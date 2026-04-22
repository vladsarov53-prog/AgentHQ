"""
Verification Gate Hook (Stop)
Проверяет ответ Claude на красные флаги перед выдачей.

Ловит фразы-маркеры неуверенности из CLAUDE.md:
"должно работать", "скорее всего", "вероятно", "по идее", "seems to".

При обнаружении: exit 2 -> Claude продолжает работу.
Проверка stop_hook_active предотвращает бесконечный цикл.

Источник: Anthropic (Stop hooks), Microsoft AgentRx (Critical Failure Step),
Google Research (17x error amplification without orchestration).
"""

import json
import sys
import re
import io

sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _read_input():
    try:
        raw = sys.stdin.buffer.read()
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}

RED_FLAGS = [
    (r"\bдолжно работать\b", "должно работать"),
    (r"\bскорее всего\b", "скорее всего"),
    (r"\bвероятно\b", "вероятно"),
    (r"\bпо идее\b", "по идее"),
    (r"\bнаверное\b", "наверное"),
    (r"\bпредположительно\b", "предположительно"),
    (r"\bне исключено\b", "не исключено"),
    (r"\bseems to\b", "seems to"),
    (r"\bshould work\b", "should work"),
    (r"\bprobably works\b", "probably works"),
]

UNCLOSED_MARKERS = [
    r"\[ДАННЫЕ ОТСУТСТВУЮТ\]",
    r"\[ТРЕБУЕТ ПРОВЕРКИ\]",
    r"\[ПРОВЕРИТЬ НОРМУ\]",
    r"\[ПРИБЛИЗИТЕЛЬНО\]",
]

MIN_RESPONSE_LENGTH = 20


def main():
    input_data = _read_input()
    if not input_data:
        sys.exit(0)

    if input_data.get("stop_hook_active", False):
        sys.exit(0)

    message = input_data.get("last_assistant_message", "")
    if not message:
        sys.exit(0)

    if len(message.strip()) < MIN_RESPONSE_LENGTH:
        sys.exit(0)

    for pattern, label in RED_FLAGS:
        if re.search(pattern, message, re.IGNORECASE):
            print(
                f"Verification Gate: обнаружен красный флаг '{label}'. "
                f"Перепроверь утверждение и замени на конкретный факт с источником.",
                file=sys.stderr,
            )
            sys.stderr.flush()
            sys.exit(2)

    marker_found = []
    for pattern in UNCLOSED_MARKERS:
        matches = re.findall(pattern, message)
        if matches:
            marker_found.extend(matches)

    if marker_found:
        markers_str = ", ".join(set(marker_found))
        print(
            f"Verification Gate: найдены незакрытые маркеры: {markers_str}. "
            f"Либо найди данные, либо явно укажи что информация недоступна.",
            file=sys.stderr,
        )
        sys.stderr.flush()
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
