"""
Agent Trace Hook (PostToolUse: any tool)
Записывает каждый вызов инструмента в operations/agent_traces.jsonl
для последующего анализа поведения агентов и производительности.

Что пишется (одна строка JSON на вызов):
- ts: timestamp ISO
- tool_name: имя инструмента (Bash, Read, Write, Task, ...)
- subagent_type: для Task — какой субагент
- input_preview: первые 200 символов tool_input (с sanitization)
- output_size_chars: размер ответа
- has_error: была ли ошибка
- file_path: только если безопасный путь (НЕ documents/contracts/personal/)

Sanitization:
- Конфиденциальные пути (contracts/personal/, .env, *.key) — путь "REDACTED"
- Полные prompt'ы и секреты не пишутся
- Только preview ~200 chars

Источник: Anthropic «Building Effective Agents» (observability как guardrail),
Google SRE Workbook (lightweight structured logging),
OpenTelemetry trace pattern (упрощённая версия без span hierarchy).
"""

import json
import os
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# Пути, содержимое которых НЕ должно попадать в трейсы
SENSITIVE_PATH_RE = re.compile(
    r"(contracts/personal|\.env|/secrets/|\.key$|\.pem$|"
    r"credentials|password|/personal/|/private/)",
    re.IGNORECASE,
)

# Регекспы потенциально чувствительных строк в input
SENSITIVE_CONTENT_RE = re.compile(
    r"(api[_-]?key|secret|password|token|bearer\s+\w+|"
    r"authorization\s*[:=])",
    re.IGNORECASE,
)

PREVIEW_LIMIT = 200


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


def sanitize_path(path):
    """Если путь sensitive — возвращает 'REDACTED', иначе сам путь."""
    if not path:
        return path
    if SENSITIVE_PATH_RE.search(str(path)):
        return "REDACTED"
    return str(path)


def sanitize_input(tool_input):
    """Возвращает безопасный preview tool_input."""
    if not tool_input:
        return ""
    if isinstance(tool_input, dict):
        # Sanitize file_path
        ti = dict(tool_input)
        if "file_path" in ti:
            ti["file_path"] = sanitize_path(ti["file_path"])
        # Скрываем длинные prompts/content
        for k in ("prompt", "content", "command", "new_string", "old_string"):
            if k in ti and isinstance(ti[k], str):
                v = ti[k][:PREVIEW_LIMIT]
                if SENSITIVE_CONTENT_RE.search(v):
                    v = "REDACTED_POSSIBLE_SECRET"
                ti[k] = v + ("..." if len(tool_input.get(k, "") or "") > PREVIEW_LIMIT else "")
        try:
            text = json.dumps(ti, ensure_ascii=False)
        except Exception:
            text = str(ti)
    else:
        text = str(tool_input)
    if SENSITIVE_CONTENT_RE.search(text):
        return "REDACTED_POSSIBLE_SECRET"
    return text[:PREVIEW_LIMIT]


def output_size(tool_response):
    """Грубая оценка размера ответа."""
    if not tool_response:
        return 0
    if isinstance(tool_response, str):
        return len(tool_response)
    try:
        return len(json.dumps(tool_response, ensure_ascii=False))
    except Exception:
        return len(str(tool_response))


def detect_error(tool_response):
    """Простая эвристика: была ли ошибка в результате."""
    if not tool_response:
        return False
    if isinstance(tool_response, dict):
        if tool_response.get("is_error"):
            return True
        for k in ("error", "errors"):
            if tool_response.get(k):
                return True
    text = json.dumps(tool_response, ensure_ascii=False) if isinstance(tool_response, (dict, list)) else str(tool_response)
    # Простые маркеры ошибок
    return bool(re.search(r"\b(error|exception|traceback|failed)\b", text[:500], re.IGNORECASE))


def main():
    input_data = _read_input()
    if not input_data:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if not tool_name:
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    tool_response = input_data.get("tool_response", {})

    # Извлекаем file_path (если есть и не sensitive)
    file_path = None
    if isinstance(tool_input, dict):
        raw_path = tool_input.get("file_path", "")
        if raw_path:
            file_path = sanitize_path(raw_path)

    subagent_type = None
    if tool_name == "Task" and isinstance(tool_input, dict):
        subagent_type = tool_input.get("subagent_type")

    event = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool_name": tool_name,
        "subagent_type": subagent_type,
        "file_path": file_path,
        "input_preview": sanitize_input(tool_input),
        "output_size_chars": output_size(tool_response),
        "has_error": detect_error(tool_response),
    }

    project_root = find_project_root()
    log_dir = project_root / "operations"
    if not log_dir.exists():
        sys.exit(0)

    log_path = log_dir / "agent_traces.jsonl"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
