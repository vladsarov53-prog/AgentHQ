"""
Output Quality Gate Hook (Stop)
Проверяет качество ответа перед выдачей:
- Факты в результате имеют источники?
- Нет ли избыточных маркеров неуверенности?
- Нет ли признаков галлюцинации?

Неблокирующий: выводит предупреждения в stderr,
но НЕ блокирует (exit 0). Дополняет verification-gate.py.

Источник: Anthropic (Building Effective Agents - guardrails),
OpenAI (Agents SDK - parallel guardrails).
"""

import json
import sys
import re


def _read_input():
    try:
        raw = sys.stdin.buffer.read()
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}

# Паттерны указания источников
SOURCE_PATTERNS = [
    r"источник:",
    r"файл[:\s]",
    r"из\s+[\w/]+\.(?:md|pdf|docx|xlsx|json)",
    r"DATA/",
    r"operations/",
    r"documents/",
    r"\.claude/skills/",
    r"memory/",
    r"RATES\.md",
    r"CALENDAR\.md",
    r"CHECKLIST\.md",
]

# Признаки галлюцинации: конкретные числа без источника
HALLUCINATION_HINTS = [
    # Суммы без контекста (500 000+ руб) - могут быть выдуманы
    r"\d{3}[\s\xa0]\d{3}[\s\xa0]\d{3}\s*(?:руб|₽)",
    # ГОСТ без проверки
    r"ГОСТ\s+\d+[-\.]\d+",
    # Статья закона без проверки
    r"[Сс]татья\s+\d+\s+[А-Я]",
    # Даты в формате ДД.ММ.ГГГГ (могут быть выдуманы)
    r"\d{2}\.\d{2}\.20\d{2}",
]

MIN_RESPONSE_FOR_CHECK = 200


def main():
    input_data = _read_input()
    if not input_data:
        sys.exit(0)

    if input_data.get("stop_hook_active", False):
        sys.exit(0)

    message = input_data.get("last_assistant_message", "")
    if not message or len(message.strip()) < MIN_RESPONSE_FOR_CHECK:
        sys.exit(0)

    warnings = []

    # 1. Проверка наличия источников в фактологических ответах
    has_numbers = bool(re.search(r"\d{3,}", message))
    has_facts = any(w in message.lower() for w in [
        "сумма", "дата", "дедлайн", "ставка", "расход",
        "бюджет", "договор", "обязательств",
    ])
    has_sources = any(re.search(p, message, re.IGNORECASE) for p in SOURCE_PATTERNS)
    has_markers = any(m in message for m in [
        "[ДАННЫЕ ОТСУТСТВУЮТ]", "[ТРЕБУЕТ ПРОВЕРКИ]",
        "[ПРОВЕРИТЬ НОРМУ]", "[ПРИБЛИЗИТЕЛЬНО]",
        "[МОЯ ИНТЕРПРЕТАЦИЯ]",
    ])

    if has_facts and has_numbers and not has_sources and not has_markers:
        warnings.append(
            "Ответ содержит факты и числа, но нет указания источника. "
            "Добавь путь к файлу или маркер неуверенности."
        )

    # 2. Проверка на возможные галлюцинации
    for pattern in HALLUCINATION_HINTS:
        matches = re.findall(pattern, message)
        if matches and not has_sources and not has_markers:
            warnings.append(
                f"Конкретные данные ({matches[0]}) без источника. "
                f"Проверь: это из файла или из общих знаний модели?"
            )
            break

    # 3. Слишком много маркеров - сигнал о нехватке данных
    marker_count = sum(
        message.count(m) for m in [
            "[ДАННЫЕ ОТСУТСТВУЮТ]", "[ТРЕБУЕТ ПРОВЕРКИ]",
            "[ПРОВЕРИТЬ НОРМУ]", "[ПРИБЛИЗИТЕЛЬНО]",
        ]
    )
    if marker_count >= 3:
        warnings.append(
            f"Найдено {marker_count} маркеров неуверенности. "
            f"Рассмотри stopping condition: запроси недостающие данные."
        )

    if warnings:
        for w in warnings:
            print(f"Quality Gate: {w}", file=sys.stderr)
        sys.stderr.flush()

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
