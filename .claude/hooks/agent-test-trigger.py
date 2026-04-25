"""
Agent Test Trigger Hook (PostToolUse: Edit/Write)
Автоматически запускает релевантные тесты при изменении промпта агента
или CLAUDE.md, чтобы предотвратить деградацию.

Что делает:
1. При изменении .claude/agents/<name>.md — запускает golden tests для
   этого агента (структурная проверка) + L0 prompt validation.
2. При изменении CLAUDE.md — запускает L0 prompt + T-0.6 settings consistency.
3. При изменении .claude/hooks/*.py — запускает L1 быстрый прогон.

Все тесты быстрые (< 5s). При проблеме — пишет в stderr (не блокирует).
Логирует результат в operations/auto_test_log.md (если папка есть).

Источник: Google DeepMind (regression gating), Anthropic (versioned prompts),
LangChain LangSmith (CI-style eval gating).
"""

import json
import os
import sys
import subprocess
import time
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
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "CLAUDE.md").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent


def normalize_path(p):
    """Нормализует путь к POSIX-стилю для матчинга."""
    return str(p).replace("\\", "/").lower()


def determine_relevant_tests(file_path, project_root):
    """
    По пути изменённого файла определяет какие тесты запускать.
    Возвращает список (test_name, script_path).
    """
    if not file_path:
        return []

    fp_norm = normalize_path(file_path)
    tests_to_run = []
    tests_dir = project_root / ".claude" / "tests"

    # 1. Изменён файл агента
    if "/.claude/agents/" in fp_norm and fp_norm.endswith(".md"):
        # Не запускать на бэкапах и тестах
        if "/backups/" in fp_norm or "/tests/" in fp_norm:
            return []
        l0_prompts = tests_dir / "L0_static" / "test_prompts.py"
        l2_golden = tests_dir / "L2_golden" / "test_golden_runner.py"
        if l0_prompts.exists():
            tests_to_run.append(("L0-prompts (agent changed)", l0_prompts))
        if l2_golden.exists():
            tests_to_run.append(("L2-golden (agent changed)", l2_golden))
        return tests_to_run

    # 2. Изменён CLAUDE.md
    if fp_norm.endswith("/claude.md"):
        l0_prompts = tests_dir / "L0_static" / "test_prompts.py"
        l3_routing = tests_dir / "L3_routing" / "test_routing.py"
        if l0_prompts.exists():
            tests_to_run.append(("L0-prompts (CLAUDE.md changed)", l0_prompts))
        if l3_routing.exists():
            tests_to_run.append(("L3-routing (CLAUDE.md changed)", l3_routing))
        return tests_to_run

    # 3. Изменён хук — только быстрая статическая проверка (L0-files: UTF-8, JSON)
    # L1 (полный прогон, 4с) запускается вручную через run_all.py, не на каждый Edit.
    if "/.claude/hooks/" in fp_norm and fp_norm.endswith(".py"):
        if fp_norm.endswith("/test_all_hooks.py") or fp_norm.endswith("/_utils.py"):
            return []
        if fp_norm.endswith("/agent-test-trigger.py"):
            return []
        l0_files = tests_dir / "L0_static" / "test_files.py"
        if l0_files.exists():
            tests_to_run.append(("L0-files (hook changed)", l0_files))
        return tests_to_run

    return []


def run_test(test_path, project_root, timeout=30):
    """Запускает тест и возвращает (ok, summary)."""
    try:
        result = subprocess.run(
            [sys.executable, str(test_path)],
            capture_output=True,
            timeout=timeout,
            cwd=str(project_root),
            # Для Windows: байты вместо текста, чтобы не падать на cp1251 stdout
        )
        ok = result.returncode == 0
        # Извлекаем summary из последних строк stdout
        try:
            stdout = result.stdout.decode("utf-8", errors="replace")
        except Exception:
            stdout = ""
        last_lines = [
            line for line in stdout.split("\n")[-10:]
            if line.strip()
        ]
        summary = " | ".join(last_lines[-2:]) if last_lines else ""
        return ok, summary[:200]
    except subprocess.TimeoutExpired:
        return False, f"timeout ({timeout}s)"
    except Exception as e:
        return False, f"error: {e}"


def append_to_log(project_root, lines):
    """Добавляет запись в operations/auto_test_log.md (если можно)."""
    log_dir = project_root / "operations"
    if not log_dir.exists():
        return
    log_path = log_dir / "auto_test_log.md"
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n## {timestamp}\n" + "\n".join(lines) + "\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass


def main():
    input_data = _read_input()
    if not input_data:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    project_root = find_project_root()
    relevant = determine_relevant_tests(file_path, project_root)

    if not relevant:
        sys.exit(0)

    failures = []
    successes = []
    log_lines = [f"- Триггер: {file_path}"]

    for name, path in relevant:
        ok, summary = run_test(path, project_root)
        if ok:
            successes.append(name)
            log_lines.append(f"  - PASS: {name}")
        else:
            failures.append((name, summary))
            log_lines.append(f"  - FAIL: {name} ({summary})")

    append_to_log(project_root, log_lines)

    if failures:
        msg_lines = [
            "[Auto-Test Trigger] Тесты упали после изменения файла:",
            f"  Файл: {file_path}",
        ]
        for name, summary in failures:
            msg_lines.append(f"  - {name}: {summary}")
        if successes:
            msg_lines.append(f"  Прошли: {', '.join(successes)}")
        msg_lines.append(
            "Проверь изменения. Это предупреждение, не блокировка."
        )
        print("\n".join(msg_lines), file=sys.stderr)
        sys.stderr.flush()

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Fail-open: не блокируем работу из-за сбоя самого триггера
        sys.exit(0)
