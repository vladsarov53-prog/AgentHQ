"""
MCP Deep Health Check (manual / on-demand)
Полный JSON-RPC handshake с каждым MCP-сервером из .mcp.json.

Что делает:
1. Парсит .mcp.json
2. Для каждого сервера: запускает subprocess, шлёт initialize-запрос
3. Ждёт ответ с timeout, парсит JSON
4. Печатает таблицу с результатами

Запускать:
    python .claude/tests/L7_monitoring/mcp_deep_check.py

Источник: MCP spec (https://spec.modelcontextprotocol.io/) — initialize handshake.
Подход: SRE deep probe (Google SRE Workbook), отдельно от shallow probe в hook.
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def find_project_root():
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "CLAUDE.md").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent.parent


def find_mcp_root(start):
    """Корень с node_modules для резолва MCP-скриптов."""
    current = start
    for _ in range(8):
        if (current / "node_modules").exists():
            return current
        if current == current.parent:
            break
        current = current.parent
    return start


def mcp_handshake(name, server_config, project_root, mcp_root, timeout_sec=10):
    """
    Запускает MCP-сервер и шлёт initialize.
    Возвращает dict: {ok, latency_ms, server_info, error}
    """
    command = server_config.get("command", "")
    args = server_config.get("args", [])

    if not command:
        return {"ok": False, "error": "no command in config"}

    # Resolve relative paths in args (для node_modules/...)
    # Сначала пробуем mcp_root (с node_modules), потом project_root.
    resolved_args = []
    for a in args:
        if any(a.endswith(ext) for ext in (".js", ".mjs", ".py")):
            p = Path(a)
            if not p.is_absolute():
                via_mcp = mcp_root / a
                via_project = project_root / a
                if via_mcp.exists():
                    p = via_mcp
                elif via_project.exists():
                    p = via_project
                else:
                    return {
                        "ok": False,
                        "error": (
                            f"скрипт {a} не найден "
                            f"(пробовал: {via_mcp}, {via_project})"
                        ),
                    }
            resolved_args.append(str(p))
        else:
            resolved_args.append(a)

    start = time.time()

    try:
        proc = subprocess.Popen(
            [command] + resolved_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(mcp_root),  # cwd = там где node_modules
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "error": f"command not found: {command}",
        }
    except Exception as e:
        return {"ok": False, "error": f"spawn failed: {e}"}

    request = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "agenthq-deep-check",
                "version": "1.0",
            },
        },
    }) + "\n"

    try:
        proc.stdin.write(request)
        proc.stdin.flush()
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        return {"ok": False, "error": f"stdin write failed: {e}"}

    response_line = {"value": None}

    def reader():
        try:
            response_line["value"] = proc.stdout.readline()
        except Exception:
            pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)

    latency_ms = int((time.time() - start) * 1000)

    try:
        proc.kill()
    except Exception:
        pass

    line = response_line["value"]
    if not line:
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "error": f"no response within {timeout_sec}s (handshake timeout)",
        }

    try:
        resp = json.loads(line)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "error": f"non-JSON response: {line[:100]}",
        }

    if "error" in resp:
        err = resp["error"]
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "error": f"server error: {err.get('message', err)}",
        }

    result = resp.get("result", {})
    server_info = result.get("serverInfo", {})

    return {
        "ok": True,
        "latency_ms": latency_ms,
        "server_info": server_info,
        "protocol_version": result.get("protocolVersion", "unknown"),
    }


def main():
    project_root = find_project_root()
    mcp_root = find_mcp_root(project_root)
    mcp_path = project_root / ".mcp.json"

    if not mcp_path.exists():
        print(f"[ERROR] .mcp.json не найден: {mcp_path}")
        sys.exit(1)

    try:
        config = json.loads(mcp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ERROR] не удалось прочитать .mcp.json: {e}")
        sys.exit(1)

    servers = config.get("mcpServers", {})
    if not servers:
        print("[INFO] .mcp.json не содержит mcpServers")
        sys.exit(0)

    print(f"\n{'='*70}")
    print(f"  MCP Deep Health Check")
    print(f"  Проект: {project_root}")
    print(f"  MCP root (node_modules): {mcp_root}")
    print(f"  Серверов: {len(servers)}")
    print(f"{'='*70}\n")

    results = []
    for name, cfg in servers.items():
        print(f"  Проверка: {name}...", end=" ", flush=True)
        r = mcp_handshake(name, cfg, project_root, mcp_root)
        results.append((name, r))
        if r["ok"]:
            srv = r.get("server_info", {})
            srv_name = srv.get("name", "?")
            srv_ver = srv.get("version", "?")
            print(
                f"OK  ({r['latency_ms']}ms) "
                f"[{srv_name} v{srv_ver}, "
                f"protocol {r.get('protocol_version', '?')}]"
            )
        else:
            print(f"FAIL  {r.get('error', 'unknown error')}")

    print(f"\n{'='*70}")
    pass_count = sum(1 for _, r in results if r["ok"])
    total = len(results)
    print(f"  Итого: {pass_count}/{total} серверов OK")
    print(f"{'='*70}\n")

    sys.exit(0 if pass_count == total else 1)


if __name__ == "__main__":
    main()
