"""
Cost Attribution Hook (PostToolUse: Task)
Атрибутирует расход токенов/символов по субагентам.

Что делает:
- Перехватывает PostToolUse для tool_name == "Task"
- Извлекает subagent_type, размер промпта и ответа
- Если в tool_response есть usage (input_tokens, output_tokens) — использует его
- Иначе оценивает по символам (~3.5 char/token эвристика)
- Пишет в operations/cost_attribution.jsonl (one event per line)

Анализ — отдельным CLI:
    python .claude/tests/L7_monitoring/cost_summary.py

Источник: Anthropic (PostToolUse hooks, token usage in API response),
Google DeepMind (per-agent attribution для multi-agent systems).
"""

import json
import sys
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


def estimate_tokens_from_chars(text):
    """Грубая эвристика: 3.5 символа = 1 токен (BPE средняя)."""
    if not text:
        return 0
    return max(1, int(len(text) / 3.5))


def extract_text_from_response(tool_response):
    """Достаёт текстовый контент из ответа Task."""
    if not tool_response:
        return ""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        # Возможные поля где может быть текст
        for key in ("content", "text", "result", "output", "message"):
            val = tool_response.get(key)
            if isinstance(val, str):
                return val
            if isinstance(val, list):
                # content часто список блоков
                pieces = []
                for item in val:
                    if isinstance(item, dict):
                        for k in ("text", "content"):
                            if isinstance(item.get(k), str):
                                pieces.append(item[k])
                    elif isinstance(item, str):
                        pieces.append(item)
                if pieces:
                    return "\n".join(pieces)
        # fallback: stringify
        try:
            return json.dumps(tool_response, ensure_ascii=False)
        except Exception:
            return str(tool_response)
    return str(tool_response)


def extract_usage(tool_response):
    """
    Пытается достать usage-метрики из tool_response.
    Возвращает dict с ключами: input_tokens, output_tokens, cache_read,
    cache_creation. None означает "недоступно".
    """
    if not isinstance(tool_response, dict):
        return None
    # Anthropic API формат: usage внутри ответа
    usage = tool_response.get("usage")
    if not isinstance(usage, dict):
        # Иногда usage в metadata
        meta = tool_response.get("metadata") or tool_response.get("meta")
        if isinstance(meta, dict):
            usage = meta.get("usage")
    if not isinstance(usage, dict):
        return None
    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
    }


def append_event(project_root, event):
    """Добавляет событие в operations/cost_attribution.jsonl."""
    log_dir = project_root / "operations"
    if not log_dir.exists():
        return
    log_path = log_dir / "cost_attribution.jsonl"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main():
    input_data = _read_input()
    if not input_data:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Task":
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    tool_response = input_data.get("tool_response", {})

    subagent_type = tool_input.get("subagent_type") or "unknown"
    description = tool_input.get("description", "")[:80]
    prompt_text = tool_input.get("prompt", "")
    response_text = extract_text_from_response(tool_response)

    usage = extract_usage(tool_response)
    if usage and usage.get("input_tokens") is not None:
        input_tokens = usage.get("input_tokens") or 0
        output_tokens = usage.get("output_tokens") or 0
        cache_read = usage.get("cache_read_input_tokens") or 0
        cache_creation = usage.get("cache_creation_input_tokens") or 0
        source = "api"
    else:
        input_tokens = estimate_tokens_from_chars(prompt_text)
        output_tokens = estimate_tokens_from_chars(response_text)
        cache_read = 0
        cache_creation = 0
        source = "estimated"

    event = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "subagent_type": subagent_type,
        "description": description,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_creation,
        "input_chars": len(prompt_text or ""),
        "output_chars": len(response_text or ""),
        "source": source,
    }

    project_root = find_project_root()
    append_event(project_root, event)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
