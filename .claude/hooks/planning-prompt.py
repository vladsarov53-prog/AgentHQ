"""
Planning Prompt Hook (UserPromptSubmit)
Анализирует запрос пользователя и при признаках multi-step задачи
добавляет в additionalContext подсказку использовать TodoWrite до маршрутизации.

Это soft enforcement — НЕ блокирует, только подсказывает. Основано на
эвристиках сложности (без LLM-классификации).

Признаки multi-step:
1. Длина: prompt > 200 символов (часто описывает несколько подзадач)
2. Маркеры последовательности: «затем», «после этого», «и потом», нумерация
3. Маркеры объёма: «несколько», «все», «полностью», списки через запятую с >2 элементов
4. Кросс-доменность: упомянуты слова из >=2 разных доменов (legal+accounting+ops+strategy)
5. Артефакты: запрос порождает несколько артефактов («презентация и письмо», «отчёт и таблица»)

Источник: Anthropic «Building Effective Agents» (Orchestrator-Workers, Planner pattern),
Google DeepMind ReAct (explicit planning), Claude Code TodoWrite tool.
"""

import json
import re
import sys

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


# Маркеры последовательности (повышают сложность)
SEQUENCE_MARKERS = [
    r"\bзатем\b", r"\bпосле этого\b", r"\bпотом\b", r"\bдальше\b",
    r"\bи потом\b", r"\bв конце\b", r"\bпосле чего\b",
    r"\bпоследовательно\b", r"\bпошагово\b",
    # Нумерация: "1)", "1.", "первое", "во-первых"
    r"^\s*1[\).]", r"\bво-первых\b", r"\bпервое\b.*\bвторое\b",
]

# Маркеры объёма (повышают сложность)
VOLUME_MARKERS = [
    r"\bнесколько\b", r"\bвсе\b", r"\bвсю\b", r"\bвсех\b",
    r"\bполностью\b", r"\bкомплексно\b", r"\bцеликом\b",
    r"\bкаждый\b", r"\bодновременно\b",
    r"\b(\d+)\s+(задач|пункт|шаг|вопрос|момент)",
]

# Доменные ключевые слова — наличие 2+ доменов = кросс-задача
DOMAINS = {
    "legal": [
        r"\bдоговор", r"\bNDA\b", r"\bакт\b", r"\bобязательств",
        r"\bIP\b", r"\bпатент", r"\bлицензи", r"\bюрид",
    ],
    "accounting": [
        r"\bбюджет", r"\bрасход", r"\bсмета", r"\bвзнос",
        r"\bналог", r"\bсчёт\b", r"\bдекларац",
        r"\bбухгалт", r"\bбурн.рейт\b", r"\bburn.rate\b",
    ],
    "operations": [
        r"\bстатус", r"\bплан\b", r"\bдедлайн", r"\bсрок",
        r"\bриск", r"\bзадач", r"\bприоритет", r"\bсписок\b",
    ],
    "strategy": [
        r"\bстратеги", r"\bразвилк", r"\bвыбор\b",
        r"\bрекомендац", r"\bзачем\b", r"\bстоит ли\b",
    ],
    "communications": [
        r"\bписьм[оа]\b", r"\bсообщени", r"\bответ\b.*\bна\b",
        r"\bотчёт", r"\bотправ", r"\bпрезентац", r"\bслайд",
        r"\bделовое\b.*\bпредложение\b",
    ],
    "engineering": [
        r"\bкод\b", r"\bбаг\b", r"\bтест\b", r"\bкомпонент",
        r"\bAPI\b", r"\bотлад", r"\bдебаг",
    ],
}

# Маркеры артефактов (несколько разных результатов)
ARTIFACT_MARKERS = [
    r"\bи\b.*\b(презентац|письм|отчёт|таблиц|документ|файл|акт)",
]

LENGTH_THRESHOLD = 200


def count_domains(prompt):
    found = set()
    for dom, patterns in DOMAINS.items():
        for p in patterns:
            if re.search(p, prompt, re.IGNORECASE):
                found.add(dom)
                break
    return found


def has_sequence(prompt):
    return any(re.search(p, prompt, re.IGNORECASE | re.MULTILINE)
               for p in SEQUENCE_MARKERS)


def has_volume(prompt):
    return any(re.search(p, prompt, re.IGNORECASE)
               for p in VOLUME_MARKERS)


def count_commas_lists(prompt):
    """Списки через запятую с 3+ элементами часто означают множественные задачи."""
    # Простая эвристика: фраза содержит >= 2 запятых вне скобок
    # и не похожа на enumerate
    n_commas = prompt.count(",")
    return n_commas >= 3


def assess_complexity(prompt):
    """
    Возвращает (score: int, reasons: list).
    Если score >= 2 → задача признаётся сложной.
    """
    if not prompt:
        return 0, []

    score = 0
    reasons = []

    if len(prompt) > LENGTH_THRESHOLD:
        score += 1
        reasons.append(f"длина {len(prompt)} символов (>{LENGTH_THRESHOLD})")

    if has_sequence(prompt):
        score += 1
        reasons.append("маркеры последовательности (затем/после/потом)")

    if has_volume(prompt):
        score += 1
        reasons.append("маркеры объёма (все/несколько/N задач)")

    domains = count_domains(prompt)
    if len(domains) >= 2:
        score += 2  # кросс-доменность — сильный сигнал
        reasons.append(f"кросс-доменность: {', '.join(sorted(domains))}")

    if count_commas_lists(prompt):
        score += 1
        reasons.append("список через запятую (3+ элементов)")

    return score, reasons


def main():
    input_data = _read_input()
    if not input_data:
        sys.exit(0)

    prompt = (
        input_data.get("prompt", "")
        or input_data.get("user_prompt", "")
    )
    if not prompt or len(prompt.strip()) < 30:
        # Слишком короткий запрос — точно не multi-step
        sys.exit(0)

    score, reasons = assess_complexity(prompt)

    if score < 2:
        # Простая задача — не вмешиваемся
        sys.exit(0)

    hint_lines = [
        "Запрос выглядит сложным (multi-step):",
    ]
    for r in reasons[:3]:
        hint_lines.append(f"  - {r}")
    hint_lines.append(
        "Рекомендуется: до маршрутизации составь план через TodoWrite "
        "(3-5 пунктов), затем выполняй последовательно."
    )

    result = {"additionalContext": "\n".join(hint_lines)}
    print(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
