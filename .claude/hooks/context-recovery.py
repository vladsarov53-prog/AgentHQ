"""
Context Recovery Hook (SessionStart/compact)
Восстанавливает критический контекст после сжатия.

При compact Claude теряет часть контекста. Этот хук
подгружает ключевые данные обратно.

Источник: Anthropic (Compact handling), CLAUDE.md (Compact Instructions).
"""

import json
import sys
from pathlib import Path


def _read_input():
    try:
        raw = sys.stdin.buffer.read()
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}


def find_project_root():
    """Ищет корень проекта по CLAUDE.md или .git."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "CLAUDE.md").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent


def get_session_log_tail(project_root, count=10):
    """Последние записи SESSION_LOG для восстановления контекста."""
    log_path = project_root / "SESSION_LOG.md"
    if not log_path.exists():
        return ""
    try:
        content = log_path.read_text(encoding="utf-8").strip()
        lines = [l for l in content.split("\n") if l.startswith("- [")]
        return "\n".join(lines[-count:])
    except OSError:
        return ""


def main():
    _read_input()  # consume stdin
    project_root = find_project_root()
    context_parts = []

    # 1. Последние изменения в сессии
    session_log = get_session_log_tail(project_root)
    if session_log:
        context_parts.append(
            f"Последние изменения в сессии:\n{session_log}"
        )

    # 2. Напоминание из CLAUDE.md (Compact Instructions)
    context_parts.append(
        "После compact сохранить:\n"
        "  - Текущая задача и формат результата\n"
        "  - Активный субагент\n"
        "  - Числовые данные (суммы, даты, сроки)\n"
        "  - Стоп-точки (удаление, отправка, деньги)\n"
        "  - Незавершённые шаги\n"
        "  - Контекст: Владислав Чадаев, RedPeak, ООО РЭДПИК"
    )

    if context_parts:
        result = {
            "additionalContext": (
                "Восстановление контекста:\n"
                + "\n".join(context_parts)
            ),
        }
        print(json.dumps(result, ensure_ascii=False))
        sys.stdout.flush()

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
