"""
L0: Проверка целостности файлов и конфигурации.
Кодировка, JSON-валидность, структура директорий.

Источник: KDD 2025 Survey (component-level testing).
"""

import os
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    PROJECT_ROOT, HOOKS_DIR, AGENTS_DIR, SKILLS_DIR, GOLDEN_TESTS_DIR,
    OPERATIONS_DIR, SETTINGS_PATH, CLAUDE_MD_PATH, AGENT_NAMES,
    CALIBRATION_LOG_PATH, SYSTEM_EVOLUTION_PATH,
)


class TestResult:
    def __init__(self, test_id, name):
        self.test_id = test_id
        self.name = name
        self.status = "PASS"
        self.details = ""

    def fail(self, details):
        self.status = "FAIL"
        self.details = details

    def warn(self, details):
        self.status = "WARN"
        self.details = details


def run_all():
    results = []

    # F-01: UTF-8 encoding в хуках
    t = TestResult("F-01", "UTF-8 encoding во всех хуках")
    hooks = [f for f in os.listdir(HOOKS_DIR) if f.endswith(".py") and not f.startswith("test_") and not f.startswith("_")]
    missing_encoding = []
    for hook in hooks:
        path = os.path.join(HOOKS_DIR, hook)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if 'reconfigure(encoding="utf-8")' not in content and "reconfigure(encoding='utf-8')" not in content:
            missing_encoding.append(hook)
    if missing_encoding:
        t.fail(f"Нет UTF-8 reconfigure: {missing_encoding}")
    else:
        t.details = f"{len(hooks)}/{len(hooks)} хуков OK"
    results.append(t)

    # F-02: settings.json валидный JSON
    t = TestResult("F-02", "settings.json валидный JSON")
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            json.load(f)
    except json.JSONDecodeError as e:
        t.fail(str(e))
    results.append(t)

    # F-03: Golden test файлы существуют
    t = TestResult("F-03", "Golden test файлы существуют")
    expected = ["accounting-agent_golden.md", "legal-agent_golden.md",
                "operations-agent_golden.md", "strategy-agent_golden.md",
                "cross-agent_golden.md"]
    if os.path.isdir(GOLDEN_TESTS_DIR):
        existing = os.listdir(GOLDEN_TESTS_DIR)
        missing = [f for f in expected if f not in existing]
        if missing:
            t.fail(f"Отсутствуют: {missing}")
        else:
            t.details = f"{len(expected)}/{len(expected)}"
    else:
        t.fail("Директория golden tests не найдена")
    results.append(t)

    # F-04: calibration_log.md содержит таблицу
    t = TestResult("F-04", "calibration_log.md содержит таблицу")
    if os.path.isfile(CALIBRATION_LOG_PATH):
        with open(CALIBRATION_LOG_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        if "| Дата |" in content or "| дата |" in content.lower():
            # Count entries
            lines = [l for l in content.split("\n") if l.startswith("| 20")]
            t.details = f"Записей: {len(lines)}"
        else:
            t.fail("Нет заголовка таблицы")
    else:
        t.fail("Файл не найден")
    results.append(t)

    # F-05: system_evolution.md содержит таблицу
    t = TestResult("F-05", "system_evolution.md содержит таблицу")
    if os.path.isfile(SYSTEM_EVOLUTION_PATH):
        with open(SYSTEM_EVOLUTION_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        if "| Дата |" in content or "| дата |" in content.lower():
            lines = [l for l in content.split("\n") if l.startswith("| 20")]
            t.details = f"Записей: {len(lines)}"
        else:
            t.fail("Нет заголовка таблицы")
    else:
        t.fail("Файл не найден")
    results.append(t)

    # F-06: Все скиллы имеют SKILL.md
    t = TestResult("F-06", "Все скиллы имеют SKILL.md")
    if os.path.isdir(SKILLS_DIR):
        skill_dirs = [d for d in os.listdir(SKILLS_DIR) if os.path.isdir(os.path.join(SKILLS_DIR, d))]
        no_skill_md = []
        for sd in skill_dirs:
            if not os.path.isfile(os.path.join(SKILLS_DIR, sd, "SKILL.md")):
                no_skill_md.append(sd)
        if no_skill_md:
            t.fail(f"Нет SKILL.md: {no_skill_md}")
        else:
            t.details = f"{len(skill_dirs)}/{len(skill_dirs)}"
    else:
        t.fail("Директория skills/ не найдена")
    results.append(t)

    # F-07: Все агент-промпты не пусты
    t = TestResult("F-07", "Все агент-промпты не пусты")
    sizes = {}
    for name in AGENT_NAMES:
        path = os.path.join(AGENTS_DIR, f"{name}.md")
        if os.path.isfile(path):
            sizes[name] = os.path.getsize(path)
        else:
            sizes[name] = 0
    empty = {k: v for k, v in sizes.items() if v < 1000}
    if empty:
        t.fail(f"Малые/пустые: {empty}")
    else:
        t.details = f"Размеры: {', '.join(f'{k}={v}B' for k, v in sizes.items())}"
    results.append(t)

    # F-08: CLAUDE.md содержит обязательные секции
    t = TestResult("F-08", "CLAUDE.md содержит обязательные секции")
    required_sections = [
        "Маршрутизация", "Антигаллюцинации", "Verification Gate",
        "Stopping conditions", "Адаптивный тон", "Learning cycle",
        "Конфиденциальность", "Оценка результата",
    ]
    if os.path.isfile(CLAUDE_MD_PATH):
        with open(CLAUDE_MD_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        missing = [s for s in required_sections if s.lower() not in content.lower()]
        if missing:
            t.fail(f"Нет секций: {missing}")
        else:
            t.details = f"{len(required_sections)}/{len(required_sections)}"
    else:
        t.fail("CLAUDE.md не найден")
    results.append(t)

    # F-09: MEMORY.md содержит индекс
    t = TestResult("F-09", "MEMORY.md содержит индекс")
    memory_md = os.path.join(
        os.path.expanduser("~"), ".claude", "projects",
        "D--REDPEAK-AgentHQ", "memory", "MEMORY.md"
    )
    if os.path.isfile(memory_md):
        with open(memory_md, "r", encoding="utf-8") as f:
            content = f.read()
        links = content.count("](")
        if links < 5:
            t.warn(f"Мало записей: {links}")
        else:
            t.details = f"{links}+ записей"
    else:
        t.warn("MEMORY.md не найден по стандартному пути")
    results.append(t)

    # F-10: Хуки не содержат синтаксических ошибок
    t = TestResult("F-10", "Хуки компилируются без ошибок")
    import py_compile
    compile_errors = []
    hooks = [f for f in os.listdir(HOOKS_DIR) if f.endswith(".py")]
    for hook in hooks:
        try:
            py_compile.compile(os.path.join(HOOKS_DIR, hook), doraise=True)
        except py_compile.PyCompileError as e:
            compile_errors.append(f"{hook}: {e}")
    if compile_errors:
        t.fail("; ".join(compile_errors))
    else:
        t.details = f"{len(hooks)}/{len(hooks)} OK"
    results.append(t)

    return results


def main():
    results = run_all()

    passed = sum(1 for r in results if r.status == "PASS")
    warned = sum(1 for r in results if r.status == "WARN")
    failed = sum(1 for r in results if r.status == "FAIL")
    total = len(results)

    print("=== L0: Целостность файлов ===\n")
    print(f"| ID | Проверка | Статус | Детали |")
    print(f"|----|----------|--------|--------|")
    for r in results:
        details = r.details[:80] if r.details else ""
        print(f"| {r.test_id} | {r.name} | {r.status} | {details} |")

    print(f"\nИтого: {passed} PASS, {warned} WARN, {failed} FAIL из {total}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
