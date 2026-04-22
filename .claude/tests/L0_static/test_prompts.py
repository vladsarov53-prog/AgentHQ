"""
L0: Статический анализ промптов агентов и конфигурации.
Проверяет структуру, обязательные секции, red flags, data contracts.

Источники: Anthropic (Bloom behavioral tests), KDD 2025 Survey.
"""

import os
import re
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    PROJECT_ROOT, AGENTS_DIR, SKILLS_DIR, BACKUPS_DIR, SETTINGS_PATH,
    CLAUDE_MD_PATH, AGENT_NAMES, AGENT_FILES, REQUIRED_AGENT_SECTIONS,
    UNCERTAINTY_MARKERS, PROMPT_RED_FLAGS, EXPECTED_HOOKS, GOLDEN_TESTS_DIR,
    OPERATIONS_DIR,
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


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def run_all():
    results = []

    # T-0.1: Обязательные секции в каждом агенте
    t = TestResult("T-0.1", "Обязательные секции в промптах агентов")
    missing = {}
    for name in AGENT_NAMES:
        content = read_file(AGENT_FILES[name])
        if content is None:
            missing[name] = ["файл не найден"]
            continue
        content_lower = content.lower()
        agent_missing = []
        for section in REQUIRED_AGENT_SECTIONS:
            if section.lower() not in content_lower:
                agent_missing.append(section)
        if agent_missing:
            missing[name] = agent_missing
    if missing:
        details = "; ".join(f"{k}: нет {v}" for k, v in missing.items())
        t.fail(details)
    results.append(t)

    # T-0.2: Red flag слова в промптах агентов
    t = TestResult("T-0.2", "Red flag слова в промптах агентов")
    found_flags = {}
    for name in AGENT_NAMES:
        content = read_file(AGENT_FILES[name])
        if content is None:
            continue
        for flag_pattern in PROMPT_RED_FLAGS:
            matches = re.findall(flag_pattern, content, re.IGNORECASE)
            if matches:
                found_flags.setdefault(name, []).extend(matches)
    if found_flags:
        details = "; ".join(f"{k}: {v}" for k, v in found_flags.items())
        t.warn(details)
    results.append(t)

    # T-0.3: Data contract consistency (fsi-report expects specific table formats)
    t = TestResult("T-0.3", "Data contract consistency (fsi-report)")
    fsi_skill = read_file(os.path.join(SKILLS_DIR, "fsi-report", "SKILL.md"))
    if fsi_skill:
        # Check accounting data contract keywords
        has_acc_contract = any(w in fsi_skill.lower() for w in [
            "статья", "план", "факт", "отклонение", "источник"
        ])
        # Check operations data contract keywords
        has_ops_contract = any(w in fsi_skill.lower() for w in [
            "веха", "milestone", "статус", "результат"
        ])
        if not has_acc_contract or not has_ops_contract:
            t.fail(f"acc_contract={has_acc_contract}, ops_contract={has_ops_contract}")
    else:
        t.fail("fsi-report/SKILL.md не найден")
    results.append(t)

    # T-0.4: Маркеры неуверенности полные в CLAUDE.md
    t = TestResult("T-0.4", "Маркеры неуверенности полные в CLAUDE.md")
    claude_md = read_file(CLAUDE_MD_PATH)
    if claude_md:
        missing_markers = [m for m in UNCERTAINTY_MARKERS if m not in claude_md]
        if missing_markers:
            t.fail(f"Отсутствуют: {missing_markers}")
    else:
        t.fail("CLAUDE.md не найден")
    results.append(t)

    # T-0.5: Stopping conditions единообразные во всех агентах
    t = TestResult("T-0.5", "Stopping conditions единообразные")
    missing_stops = []
    for name in AGENT_NAMES:
        content = read_file(AGENT_FILES[name])
        if content is None:
            continue
        content_lower = content.lower()
        has_file_limit = bool(re.search(r"(?:5|пять)\s*(?:файл|обращени|запрос)", content_lower))
        has_marker_limit = bool(re.search(r"(?:3|три|трёх)\s*(?:маркер|\[данные)", content_lower))
        if not has_file_limit or not has_marker_limit:
            missing_stops.append(f"{name}: file_limit={has_file_limit}, marker_limit={has_marker_limit}")
    if missing_stops:
        t.warn("; ".join(missing_stops))
    results.append(t)

    # T-0.6: Settings.json hooks целостность
    t = TestResult("T-0.6", "Settings.json hooks целостность")
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)
        hooks = settings.get("hooks", {})
        missing_hooks = []
        for event_type, expected_scripts in EXPECTED_HOOKS.items():
            if event_type not in hooks:
                missing_hooks.append(f"{event_type} отсутствует")
                continue
            registered = []
            for entry in hooks[event_type]:
                for h in entry.get("hooks", []):
                    cmd = h.get("command", "")
                    for script in expected_scripts:
                        if script in cmd:
                            registered.append(script)
            for script in expected_scripts:
                if script not in registered:
                    missing_hooks.append(f"{event_type}/{script} не зарегистрирован")
        if missing_hooks:
            t.fail("; ".join(missing_hooks))
    except Exception as e:
        t.fail(str(e))
    results.append(t)

    # T-0.7: Backup files существуют и не пусты
    t = TestResult("T-0.7", "Backup files существуют и не пусты")
    if os.path.isdir(BACKUPS_DIR):
        backup_files = [f for f in os.listdir(BACKUPS_DIR) if f.endswith(".md")]
        if len(backup_files) < 4:
            t.fail(f"Найдено {len(backup_files)} бэкапов, ожидается >= 4")
        else:
            empty_backups = []
            for bf in backup_files:
                path = os.path.join(BACKUPS_DIR, bf)
                size = os.path.getsize(path)
                if size < 5000:
                    empty_backups.append(f"{bf}: {size}B")
            if empty_backups:
                t.fail(f"Малые бэкапы: {empty_backups}")
    else:
        t.fail("Директория backups/ не найдена")
    results.append(t)

    # T-0.8: SKILL.md intake section
    t = TestResult("T-0.8", "SKILL.md имеют секцию intake/вход")
    no_intake = []
    if os.path.isdir(SKILLS_DIR):
        for skill_name in os.listdir(SKILLS_DIR):
            skill_path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
            if os.path.isfile(skill_path):
                content = read_file(skill_path)
                if content:
                    content_lower = content.lower()
                    has_intake = any(w in content_lower for w in [
                        "intake", "вход", "входные", "параметры запроса",
                        "что нужно", "принимает", "запрос содержит",
                    ])
                    if not has_intake:
                        no_intake.append(skill_name)
    if no_intake:
        t.warn(f"Без intake: {no_intake}")
    results.append(t)

    # T-0.9: Cross-references: скиллы из CLAUDE.md существуют
    t = TestResult("T-0.9", "Cross-references: скиллы из CLAUDE.md существуют")
    if claude_md:
        # Extract skill references like **skill-name** or skill-name
        skill_refs = set(re.findall(r"\*\*([a-z][\w-]+)\*\*", claude_md))
        # Filter to actual skill names (not agent names, not generic words)
        existing_skills = set()
        if os.path.isdir(SKILLS_DIR):
            existing_skills = set(os.listdir(SKILLS_DIR))
        # Only check references that look like skill names
        missing_skills = []
        for ref in skill_refs:
            if ref in ("operations-agent", "legal-agent", "accounting-agent", "strategy-agent"):
                continue
            if ref.endswith("-agent"):
                continue
            # Check if it's a skill reference
            if ref in ("anthropic-skills", "claude-api", "frontend-design", "webapp-testing",
                       "systematic-debugging", "meeting-prep", "pitch-deck", "contract-review",
                       "fsi-report", "grant-tracker", "decision-log", "risk-log", "weekly-status",
                       "email-draft", "humanizer", "competitor-watch", "code-review-brief",
                       "onboarding-brief", "task-card", "strategy-agent", "accounting-agent"):
                # These should exist in skills dir
                normalized = ref
                if normalized not in existing_skills:
                    missing_skills.append(normalized)
        if missing_skills:
            t.warn(f"Скиллы не найдены: {missing_skills}")
    results.append(t)

    return results


def main():
    results = run_all()

    passed = sum(1 for r in results if r.status == "PASS")
    warned = sum(1 for r in results if r.status == "WARN")
    failed = sum(1 for r in results if r.status == "FAIL")
    total = len(results)

    print("=== L0: Статический анализ промптов ===\n")
    print(f"| ID | Проверка | Статус | Детали |")
    print(f"|----|----------|--------|--------|")
    for r in results:
        details = r.details[:80] if r.details else ""
        print(f"| {r.test_id} | {r.name} | {r.status} | {details} |")

    print(f"\nИтого: {passed} PASS, {warned} WARN, {failed} FAIL из {total}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
