"""
Session Log Hook (PostToolUse)
Логирует изменения файлов в SESSION_LOG.md.

Неблокирующий: всегда exit 0. Ведёт аудит
какие файлы были созданы или изменены в сессии.
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def _read_input():
    try:
        raw = sys.stdin.buffer.read()
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}

SKIP_PATHS = [".claude/", "node_modules/", ".git/", "__pycache__/"]


def find_project_root():
    """Ищет корень проекта по CLAUDE.md или .git."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "CLAUDE.md").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent


def main():
    input_data = _read_input()
    if not input_data:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path:
        sys.exit(0)

    # Пропускаем служебные пути
    file_path_str = str(file_path).replace("\\", "/")
    for skip in SKIP_PATHS:
        if skip in file_path_str:
            sys.exit(0)

    project_root = find_project_root()
    log_path = project_root / "SESSION_LOG.md"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    filename = Path(file_path).name
    action = "Edit" if tool_name == "Edit" else "Write"

    entry = f"- [{timestamp}] {action}: {filename} ({file_path_str})\n"

    try:
        if not log_path.exists():
            log_path.write_text(
                f"# Session Log\n\n{entry}", encoding="utf-8"
            )
        else:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry)
    except OSError:
        pass  # Не блокируем работу из-за ошибки логирования

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
