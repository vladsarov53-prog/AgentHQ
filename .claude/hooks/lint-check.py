"""
Lint Check Hook (PostToolUse)
Проверяет синтаксис файлов после создания/редактирования.

Неблокирующий: всегда exit 0. Результат проверки
передается Claude через stdout JSON как additionalContext.
"""

import json
import sys
import subprocess
from pathlib import Path


def _read_input():
    try:
        raw = sys.stdin.buffer.read()
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}

SKIP = [".claude/", "node_modules/", ".git/"]
SUPPORTED = {".py", ".js", ".json"}


def check_python(file_path):
    try:
        result = subprocess.run(
            ["python", "-m", "py_compile", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip()
            return False, error
        return True, None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return True, None


def check_javascript(file_path):
    try:
        result = subprocess.run(
            ["node", "--check", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip()
            return False, error
        return True, None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return True, None


def check_json(file_path):
    try:
        with open(file_path, encoding="utf-8") as f:
            json.load(f)
        return True, None
    except json.JSONDecodeError as e:
        return False, f"JSON: строка {e.lineno}, колонка {e.colno}: {e.msg}"
    except OSError:
        return True, None


CHECKERS = {
    ".py": check_python,
    ".js": check_javascript,
    ".json": check_json,
}


def main():
    input_data = _read_input()
    if not input_data:
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    file_path_str = str(file_path).replace("\\", "/")
    for skip in SKIP:
        if skip in file_path_str:
            sys.exit(0)

    ext = Path(file_path).suffix.lower()
    if ext not in SUPPORTED:
        sys.exit(0)

    checker = CHECKERS.get(ext)
    if not checker:
        sys.exit(0)

    ok, error = checker(file_path)
    filename = Path(file_path).name

    if ok:
        result = {
            "additionalContext": f"Lint: {filename} - OK"
        }
    else:
        result = {
            "additionalContext": f"Lint: синтаксическая ошибка в {filename}: {error}"
        }
        print(
            f"Синтаксическая ошибка в {filename}: {error}",
            file=sys.stderr,
        )

    print(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
