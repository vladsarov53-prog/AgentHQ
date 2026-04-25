"""
Memory Index Hook (PostToolUse: Write/Edit)
Автоматически индексирует изменённые файлы auto-memory в Chroma.

Срабатывает только если:
- tool_name == Write/Edit
- file_path внутри auto-memory dir
- file_path заканчивается на .md и не равен MEMORY.md

Запускает reindex_one.py через venv с chromadb (сам этот хук не зависит
от chromadb — fail-open, чтобы любая ошибка venv не блокировала пользователя).

Источник: Anthropic PostToolUse hooks, retrieval-augmented memory pattern.
"""

import json
import os
import subprocess
import sys
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


def is_auto_memory_path(file_path):
    """Проверяет что путь — внутри auto-memory dir (любого projects/<slug>/memory/)."""
    if not file_path:
        return False
    norm = str(file_path).replace("\\", "/").lower()
    if not norm.endswith(".md"):
        return False
    if norm.endswith("/memory.md"):
        return False
    # Эвристика: содержит /.claude/projects/.../memory/
    return "/.claude/projects/" in norm and "/memory/" in norm


def main():
    input_data = _read_input()
    if not input_data:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if not is_auto_memory_path(file_path):
        sys.exit(0)

    project_root = find_project_root()
    venv_python = project_root / ".claude" / "venv_chroma" / "Scripts" / "python.exe"
    reindex_one = (
        project_root / ".claude" / "tests" / "L7_monitoring" / "reindex_one.py"
    )

    if not venv_python.exists() or not reindex_one.exists():
        # Инфраструктура ещё не установлена — молча пропускаем
        sys.exit(0)

    try:
        # Тихий запуск — не отвлекаем пользователя
        subprocess.run(
            [str(venv_python), str(reindex_one), file_path],
            timeout=15,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        # Не критично, переиндексируется при следующем запуске reindex
        pass
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
