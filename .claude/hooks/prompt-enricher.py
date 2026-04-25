"""
Prompt Enricher Hook (UserPromptSubmit)
Автоматически добавляет рекомендации к пользовательским
запросам: файлы/директории связанные с задачей.

Снижает вероятность context_missing: агент сразу получает
подсказки о контексте, а не ищет вслепую.

Источник: Harrison Chase (Context Engineering),
Anthropic UserPromptSubmit docs.
"""

import json
import sys
import re

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


ROUTE_MAP = [
    {
        "patterns": [
            r"договор", r"NDA", r"акт\b", r"контракт",
            r"юрид", r"обязательств", r"неустойк",
        ],
        "hint": (
            "Искать документы в DATA/Договоры/ и DATA/NDA/."
            " Релевантные файлы: legal/"
        ),
    },
    {
        "patterns": [
            r"расход", r"бюджет", r"бухгалт", r"смет[аы]",
            r"платёж", r"счёт\b", r"взнос", r"НДФЛ",
        ],
        "hint": (
            "Искать документы в DATA/Бухгалтер/ и DATA/Грант/."
            " Каталог: finance/. Операционные данные: operations/"
        ),
    },
    {
        "patterns": [
            r"статус", r"план\b", r"приоритет",
            r"задач", r"неделя", r"спринт", r"risk",
        ],
        "hint": (
            "operations/ (calibration_log, risk_log)."
            " Память: memory/."
            " SESSION_LOG.md для контекста последних действий"
        ),
    },
    {
        "patterns": [
            r"налог", r"деклара", r"ФНС", r"СФР",
            r"ОСНО", r"льгот", r"нулев",
        ],
        "hint": (
            "Искать документы в DATA/Налоговая ООО/ и tax/."
            " Каталог: finance/. Первый приоритет: бухгалтер"
        ),
    },
    {
        "patterns": [
            r"грант", r"ФСИ", r"Сколков",
            r"Старт.?ЦТ", r"отчёт.*грант",
        ],
        "hint": (
            "DATA/Грант/. Навыки: grant-tracker, fsi-report."
            " Релевантны к грантам и ФСИ"
        ),
    },
    {
        "patterns": [
            r"письм[оа]", r"email",
            r"написать\b.*кому", r"ответ\b.*на\b",
            r"сообщени",
        ],
        "hint": (
            "documents/comms/ для примеров."
            " Включить скилл humanizer для тона текста."
            " Уточнить тон: партнёры/команда/ФСИ/Сколково"
        ),
    },
    {
        "patterns": [
            r"презентац", r"слайд", r"pitch",
            r"deck", r"инвестор",
        ],
        "hint": (
            "DATA/Образцовый спитч/ для референсов."
            " Скилл pitch-deck для контента,"
            " anthropic-skills:pptx для файла"
        ),
    },
    {
        "patterns": [
            r"конкурент", r"рынок\b",
            r"аналог", r"сравн.*продукт",
        ],
        "hint": (
            "DATA/ для данных. Скилл competitor-watch."
            " Используй веб-поиск для актуальных данных"
        ),
    },
]


def main():
    input_data = _read_input()
    if not input_data:
        sys.exit(0)

    prompt = (
        input_data.get("prompt", "")
        or input_data.get("user_prompt", "")
    )
    if not prompt:
        sys.exit(0)

    matched_hints = []
    for route in ROUTE_MAP:
        for pattern in route["patterns"]:
            if re.search(pattern, prompt, re.IGNORECASE):
                matched_hints.append(route["hint"])
                break

    if matched_hints:
        result = {
            "additionalContext": (
                "Подсказки по контексту:\n"
                + "\n".join(f"  - {h}" for h in matched_hints)
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
