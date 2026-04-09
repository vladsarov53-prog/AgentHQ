"""
L4: Integration tests - E2E workflow definitions.
Определяет сценарии для ручного/LLM-as-judge тестирования.

Эти тесты НЕ запускают агентов автоматически (это требует LLM).
Вместо этого они определяют test cases, checklists и grading rubrics
для выполнения оператором или через LLM-as-judge.

Источник: Google DeepMind (multi-hop), OpenAI (50-step sequences).
"""

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECT_ROOT


WORKFLOW_TESTS = [
    {
        "id": "T-4.1",
        "name": "Понедельничный брифинг (E2E)",
        "prompt": "Понедельничный брифинг на эту неделю",
        "expected_flow": [
            "Cold start protocol (загрузка контекста из памяти)",
            "operations-agent: статусы задач, дедлайны",
            "accounting-agent: burn rate, расходы",
            "strategy-agent: анализ поверх данных ops+acc",
            "Выдача: 6 блоков (Фокус, Рекомендации, Упущенное, Ранние сигналы, Q&A, Эволюция)",
        ],
        "parallelization": "ops || acc -> strategy (sequential after)",
        "checklist": [
            "6 блоков присутствуют",
            "Каждая рекомендация: действие + источник + последствие + уровень уверенности",
            "Блок эволюции на данных calibration_log (или 'недостаточно данных')",
            "Нет абстрактных советов без привязки к контексту",
            "Все источники конкретные (файл или memory ID)",
        ],
        "red_flags": [
            "Рекомендации без источников",
            "Нет уровней уверенности [ВЫСОКАЯ]/[СРЕДНЯЯ]/[ГИПОТЕЗА]",
            "Дублирование работы operations-agent",
            "Блок эволюции на 'общих мыслях' вместо calibration_log",
        ],
    },
    {
        "id": "T-4.2",
        "name": "Подготовка отчёта ФСИ (cross-agent)",
        "prompt": "Подготовь данные для промежуточного отчёта по гранту ФСИ",
        "expected_flow": [
            "Dispatcher определяет кросс-ролевую задачу",
            "accounting-agent: расходы по статьям бюджета (план/факт/отклонение/источник)",
            "operations-agent: статус вех (веха/дата/статус/результат/источник)",
            "Dispatcher собирает результаты по шаблону fsi-report",
            "Проверка по CHECKLIST.md",
        ],
        "parallelization": "accounting || operations -> dispatcher (sequential assembly)",
        "data_contracts": {
            "accounting_output": "| Статья | План | Факт | Отклонение | Док-источник |",
            "operations_output": "| Веха | Плановая дата | Статус | Результат | Источник |",
        },
        "checklist": [
            "Оба субагента запущены",
            "Параллельное выполнение (не последовательное)",
            "Data contracts соблюдены (формат таблиц)",
            "Источники в каждой строке таблицы",
            "Dispatcher собрал единый документ",
        ],
        "red_flags": [
            "Один субагент вместо двух",
            "Последовательный вызов вместо параллельного",
            "Расхождение данных между субагентами",
            "Отсутствие сборки диспетчером",
        ],
    },
    {
        "id": "T-4.3",
        "name": "Анализ нового договора с бюджетом",
        "prompt": "Проанализируй новый договор и проверь совместимость с бюджетом гранта",
        "expected_flow": [
            "legal-agent: анализ обязательств (пункты, стороны, суть, сроки)",
            "accounting-agent: сверка суммы с бюджетом гранта",
            "Dispatcher: рекомендация (юрид. + бюджетная совместимость)",
        ],
        "parallelization": "legal || accounting -> dispatcher recommendation",
        "checklist": [
            "Таблица обязательств с точными пунктами договора",
            "Сверка суммы договора с остатком бюджета",
            "Итоговая рекомендация учитывает оба аспекта",
        ],
        "red_flags": [
            "Пункты договора без ссылки на конкретный файл",
            "Бюджетные данные без источника",
            "Рекомендация без учёта одного из аспектов",
        ],
    },
    {
        "id": "T-4.4",
        "name": "Кризисный сценарий (3 срочных задачи)",
        "prompt": "Срочно: 1) ФСИ запросила промежуточный отчёт до пятницы, 2) контрагент просит подписать допсоглашение, 3) бухгалтер спрашивает по дедлайну ФНС",
        "expected_flow": [
            "Приоритизация 3 задач (strategy или dispatcher)",
            "Intake по каждой задаче (уточнение если нужно)",
            "Параллелизация: independent tasks in parallel",
            "Каждая задача -> соответствующий субагент",
        ],
        "checklist": [
            "Все 3 задачи обработаны",
            "Приоритизация (какая первая)",
            "Параллельное выполнение независимых задач",
            "Intake-вопросы где нужно",
        ],
        "red_flags": [
            "Пропущена одна из 3 задач",
            "Все задачи последовательно (если есть независимые)",
            "Нет приоритизации",
        ],
    },
]

MEMORY_TESTS = [
    {
        "id": "T-4.5",
        "name": "Запись decision entity",
        "scenario": "Руководитель принял решение использовать Gemini вместо OpenRouter",
        "expected": {
            "type": "decision",
            "required_fields": ["тип", "дата", "суть", "источник", "статус"],
            "confirmation_required": True,
            "needs_review": False,
        },
    },
    {
        "id": "T-4.6",
        "name": "Запись obligation с дедлайном",
        "scenario": "Отчёт ФСИ нужно сдать до 15 июня 2026",
        "expected": {
            "type": "obligation",
            "date_format": "absolute (YYYY-MM-DD)",
            "confirmation_required": True,
        },
    },
    {
        "id": "T-4.7",
        "name": "Обнаружение противоречия в памяти",
        "scenario": "Существует запись 'бюджет гранта 5 млн', новая информация 'бюджет гранта 4 млн'",
        "expected": {
            "action": "показать конфликт руководителю",
            "auto_overwrite": False,
        },
    },
    {
        "id": "T-4.8",
        "name": "Целевой запрос к памяти",
        "scenario": "Нужны текущие обязательства",
        "expected": {
            "query_type": "targeted (obligations + status=current)",
            "full_dump": False,
        },
    },
    {
        "id": "T-4.9",
        "name": "needs_review маркировка",
        "scenario": "Запиши что дедлайн ФСИ 1 мая (руководитель сказал, документа нет)",
        "expected": {
            "needs_review": True,
            "source": "указание руководителя",
        },
    },
]

VERIFICATION_GATE_TESTS = [
    {
        "id": "T-4.14",
        "name": "Субагент выдаёт 'готово' без источников",
        "expected": "Dispatcher не доверяет, перепроверяет",
    },
    {
        "id": "T-4.15",
        "name": "Результат с 3+ [ДАННЫЕ ОТСУТСТВУЮТ]",
        "expected": "Stop condition, показ списка недостающего",
    },
    {
        "id": "T-4.16",
        "name": "Critical task (legal) двойной ревью",
        "expected": "Self-check субагента + dispatcher independent check",
    },
]


def run_all():
    print("=== L4: Integration & E2E Tests ===\n")

    total = 0

    # Workflow tests
    print("### E2E Workflows\n")
    for wf in WORKFLOW_TESTS:
        total += 1
        print(f"  REF   {wf['id']} {wf['name']}")
        print(f"         Prompt: \"{wf['prompt'][:60]}\"")
        print(f"         Flow: {len(wf['expected_flow'])} шагов")
        if "parallelization" in wf:
            print(f"         Parallel: {wf['parallelization']}")
        print(f"         Checklist: {len(wf['checklist'])} пунктов")
        print(f"         Red flags: {len(wf['red_flags'])} паттернов")
        print()

    # Memory tests
    print("### Memory System Tests\n")
    for mt in MEMORY_TESTS:
        total += 1
        print(f"  REF   {mt['id']} {mt['name']}")
        print(f"         Scenario: {mt['scenario'][:60]}")
        print(f"         Expected: {mt['expected']}")
        print()

    # Verification gate integration
    print("### Verification Gate Integration\n")
    for vt in VERIFICATION_GATE_TESTS:
        total += 1
        print(f"  REF   {vt['id']} {vt['name']}")
        print(f"         Expected: {vt['expected']}")
        print()

    print(f"{'='*50}")
    print(f"L4 Integration: {total} test cases defined (golden reference)")
    print(f"Для выполнения: прогнать prompts вручную или через LLM-as-judge")
    print(f"{'='*50}")

    return 0


if __name__ == "__main__":
    sys.exit(run_all())
