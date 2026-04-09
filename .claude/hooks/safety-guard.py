"""
Safety Guard Hook (PreToolUse)
Блокирует опасные терминальные команды.

Если Claude пытается выполнить rm -rf, force push,
или запустить скрипт из интернета, хук останавливает выполнение.
"""

import json
import sys
import re

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BLOCK_PATTERNS = [
    # rm -rf / или rm -rf ~ (но НЕ rm -rf ./dir/)
    (
        r'rm\s+(?:-[a-zA-Z]*r[a-zA-Z]*\s+(?:-[a-zA-Z]*f[a-zA-Z]*\s+)?|(?:-[a-zA-Z]*f[a-zA-Z]*\s+)?-[a-zA-Z]*r[a-zA-Z]*\s+)[/~]',
        "ЗАБЛОКИРОВАНО: рекурсивное удаление корневой/домашней директории запрещено"
    ),
    # rm -rf ~ (тильда отдельно)
    (
        r'rm\s+(?:-[a-zA-Z]*rf[a-zA-Z]*|-[a-zA-Z]*fr[a-zA-Z]*)\s+~',
        "ЗАБЛОКИРОВАНО: рекурсивное удаление домашней директории запрещено"
    ),
    # git push --force / git push -f (но НЕ --force-with-lease)
    (
        r'git\s+push\s+.*(?:--force(?!-with-lease)|-f(?:\s|$))',
        "ЗАБЛОКИРОВАНО: принудительный push (--force) запрещен. Используйте --force-with-lease или обычный push"
    ),
    # git reset --hard
    (
        r'git\s+reset\s+--hard',
        "ЗАБЛОКИРОВАНО: git reset --hard запрещен. Используйте --soft или --mixed"
    ),
    # git clean
    (
        r'git\s+clean\b',
        "ЗАБЛОКИРОВАНО: git clean запрещен. Удаляйте файлы явно"
    ),
    # curl ... | bash / wget ... | bash
    (
        r'curl\s.*\|\s*(?:ba)?sh',
        "ЗАБЛОКИРОВАНО: выполнение скриптов из интернета через pipe запрещено"
    ),
    (
        r'wget\s.*\|\s*(?:ba)?sh',
        "ЗАБЛОКИРОВАНО: выполнение скриптов из интернета через pipe запрещено"
    ),
    # npm publish
    (
        r'npm\s+publish\b',
        "ЗАБЛОКИРОВАНО: npm publish запрещен. Публикация только вручную"
    ),
    # DROP TABLE / DROP DATABASE
    (
        r'DROP\s+TABLE',
        "ЗАБЛОКИРОВАНО: DROP TABLE запрещен"
    ),
    (
        r'DROP\s+DATABASE',
        "ЗАБЛОКИРОВАНО: DROP DATABASE запрещен"
    ),
    # Windows: format drive
    (
        r'format\s+[A-Za-z]:',
        "ЗАБЛОКИРОВАНО: форматирование диска запрещено"
    ),
    # Windows: recursive delete with /s /q
    (
        r'(?:del|erase)\s+/[a-zA-Z]*s[a-zA-Z]*\s+/[a-zA-Z]*q',
        "ЗАБЛОКИРОВАНО: рекурсивное удаление файлов запрещено"
    ),
    # Windows: rd /s /q (remove directory)
    (
        r'(?:rd|rmdir)\s+/[a-zA-Z]*s[a-zA-Z]*\s+/[a-zA-Z]*q',
        "ЗАБЛОКИРОВАНО: рекурсивное удаление директорий запрещено"
    ),
    # PowerShell: Remove-Item -Recurse -Force on root/home
    (
        r'Remove-Item\s+.*-Recurse.*-Force.*[/\\][A-Za-z]:[/\\]?(?:\s|$)',
        "ЗАБЛОКИРОВАНО: PowerShell рекурсивное удаление корневого каталога запрещено"
    ),
    # diskpart
    (
        r'\bdiskpart\b',
        "ЗАБЛОКИРОВАНО: diskpart запрещен. Управление дисками только вручную"
    ),
    # curl/wget pipe to any interpreter (python, perl, ruby, node)
    (
        r'(?:curl|wget)\s.*\|\s*(?:python|perl|ruby|node)',
        "ЗАБЛОКИРОВАНО: выполнение скриптов из интернета через pipe запрещено"
    ),
    # dd if=/dev/zero (disk destruction)
    (
        r'\bdd\s+.*if=/dev/(?:zero|random|urandom)\s+.*of=/dev/',
        "ЗАБЛОКИРОВАНО: запись на блочное устройство через dd запрещена"
    ),
    # mkfs (format filesystem)
    (
        r'\bmkfs\b',
        "ЗАБЛОКИРОВАНО: создание файловой системы (mkfs) запрещено"
    ),
]


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name != "Bash":
        sys.exit(0)

    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)

    for pattern, message in BLOCK_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            print(message, file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(
            f"Safety guard error: {e}. Blocking command by default (fail-closed).",
            file=sys.stderr,
        )
        sys.exit(2)
