"""
MCP Health Check Hook (SessionStart)
Быстрая проверка инфраструктуры MCP-серверов при старте сессии.

Что проверяет (< 200ms, не блокирует):
1. .mcp.json существует и валиден.
2. Для каждого MCP-сервера: команда (node/python) доступна в PATH.
3. Файлы dist/index.js (или путь из args) существуют.
4. Для memory-сервера: knowledge_graph.json валидный JSON.

При проблеме: возвращает additionalContext с предупреждением,
но НЕ блокирует старт сессии. Claude видит warning и может предупредить.

Источник: Anthropic SessionStart hooks, Google SRE Workbook
(health checks как "shallow probe" + manual deep probe).
"""

import json
import sys
import shutil
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def _read_input():
    try:
        raw = sys.stdin.buffer.read()
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}


def find_project_root():
    """Корень для CLAUDE.md/operations/memory (может быть worktree)."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "CLAUDE.md").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent


def find_mcp_root(start):
    """
    Корень с node_modules для резолва путей MCP-серверов.
    В worktree node_modules может не быть — поднимаемся к основному проекту.
    Если не нашли — возвращаем исходный start.
    """
    current = start
    for _ in range(8):  # safety limit
        if (current / "node_modules").exists():
            return current
        if current == current.parent:
            break
        current = current.parent
    return start


def load_mcp_config(project_root):
    """Загружает .mcp.json. Возвращает dict или None."""
    mcp_path = project_root / ".mcp.json"
    if not mcp_path.exists():
        return None
    try:
        return json.loads(mcp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def resolve_arg_path(arg, project_root, mcp_root):
    """
    Преобразует путь из args в абсолютный.
    Пробует mcp_root (с node_modules), потом project_root (worktree).
    """
    p = Path(arg)
    if p.is_absolute():
        return p
    via_mcp = mcp_root / arg
    if via_mcp.exists():
        return via_mcp
    return project_root / arg


def check_server(name, server_config, project_root, mcp_root):
    """Проверяет один MCP-сервер. Возвращает (ok, problems: list)."""
    problems = []
    command = server_config.get("command", "")
    args = server_config.get("args", [])

    # 1. Команда доступна?
    if not command:
        problems.append(f"{name}: нет 'command' в конфиге")
        return False, problems

    if shutil.which(command) is None:
        problems.append(
            f"{name}: команда '{command}' не найдена в PATH"
        )
        return False, problems

    # 2. Первый arg обычно — путь к скрипту. Проверяем существование.
    if args:
        first_arg = args[0]
        # Эвристика: если выглядит как путь к файлу (.js/.py/.mjs)
        if any(first_arg.endswith(ext) for ext in (".js", ".mjs", ".py")):
            script_path = resolve_arg_path(first_arg, project_root, mcp_root)
            if not script_path.exists():
                problems.append(
                    f"{name}: скрипт {first_arg} не найден "
                    f"(пробовал: {mcp_root / first_arg}, {project_root / first_arg})"
                )
                return False, problems

    return True, problems


def check_memory_data(project_root):
    """Проверяет валидность данных memory MCP."""
    problems = []

    # knowledge_graph.json — основной файл server-memory
    kg_paths = [
        project_root / "memory" / "knowledge_graph.json",
        project_root / "memory" / "knowledge.jsonl",
    ]

    for kg_path in kg_paths:
        if not kg_path.exists():
            continue
        try:
            content = kg_path.read_text(encoding="utf-8").strip()
            if not content:
                continue  # пустой файл — это норма для свежей системы
            if kg_path.suffix == ".json":
                json.loads(content)
            else:  # .jsonl
                for i, line in enumerate(content.split("\n"), 1):
                    if line.strip():
                        json.loads(line)
        except json.JSONDecodeError as e:
            problems.append(
                f"memory: {kg_path.name} повреждён "
                f"(JSON ошибка: {str(e)[:80]})"
            )
        except OSError as e:
            problems.append(
                f"memory: не удалось прочитать {kg_path.name}: {e}"
            )

    return problems


def main():
    _read_input()
    project_root = find_project_root()
    mcp_root = find_mcp_root(project_root)

    config = load_mcp_config(project_root)
    if config is None:
        # Нет .mcp.json — это либо нормальная конфигурация без MCP,
        # либо файл удалили. Не делаем выводов, не шумим.
        sys.exit(0)

    servers = config.get("mcpServers", {})
    if not servers:
        sys.exit(0)

    all_problems = []
    ok_servers = []

    for name, server_config in servers.items():
        ok, problems = check_server(name, server_config, project_root, mcp_root)
        if ok:
            ok_servers.append(name)
        else:
            all_problems.extend(problems)

    # Дополнительная проверка данных для memory-сервера
    if "memory" in servers:
        all_problems.extend(check_memory_data(project_root))

    if all_problems:
        warning = "[MCP Health] Обнаружены проблемы:\n" + "\n".join(
            f"  - {p}" for p in all_problems
        )
        if ok_servers:
            warning += f"\nРаботают: {', '.join(ok_servers)}"
        warning += (
            "\nСистема продолжит работу, но операции с MCP "
            "(память/файлы) могут не работать. "
            "Запусти deep-check: python .claude/tests/L7_monitoring/mcp_deep_check.py"
        )
        result = {"additionalContext": warning}
        print(json.dumps(result, ensure_ascii=False))
        sys.stdout.flush()

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Fail-open: ошибка в health-check не должна блокировать сессию
        sys.exit(0)
