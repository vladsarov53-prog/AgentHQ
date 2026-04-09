"""
Subagent Context Injection Hook (SubagentStart)
Автоматически подгружает контекст для каждого субагента.

Реализует Compound Knowledge Base: подгружает прошлые ошибки
и правила для конкретного субагента из calibration_log.md.

Источник: Harrison Chase (Context Engineering),
OpenAI (Self-Evolving Agents), Anthropic Sub-agents docs.
"""

import json
import sys
from pathlib import Path

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def find_project_root():
    """Ищет корень проекта по CLAUDE.md или .git."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "CLAUDE.md").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent


def get_agent_errors(project_root, agent_name):
    """Загружает прошлые ошибки для конкретного субагента."""
    cal_path = project_root / "operations" / "calibration_log.md"
    if not cal_path.exists():
        print(f"subagent-context: calibration_log not found at {cal_path}", file=sys.stderr)
        return ""
    try:
        content = cal_path.read_text(encoding="utf-8").strip()
        errors = []
        for line in content.split("\n"):
            if "| дата" in line.lower() or "|---" in line:
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 5 and agent_name.lower() in line.lower():
                errors.append(line.strip())
        return "\n".join(errors[-5:])
    except OSError as e:
        print(f"subagent-context: error reading {cal_path}: {e}", file=sys.stderr)
        return ""


AGENT_CONTEXT = {
    "Explore": (
        "Структура проекта AgentHQ:\n"
        "  - DATA/ - данные проекта (договоры, гранты, патенты)\n"
        "  - operations/ - статусы, планы, risk log\n"
        "  - .claude/agents/ - промпты субагентов\n"
        "  - .claude/skills/ - скиллы\n"
        "  - ai-news-bot/ - Python бот\n"
    ),
    "general": (
        "Проект: RedPeak (CAD-модуль проверки).\n"
        "Команда: 4 человека. Грант ФСИ 5 млн (ожидание).\n"
        "Статус Сколково: одобрен.\n"
        "Язык: русский. Все результаты на русском.\n"
    ),
    "accounting": (
        "Контекст: accounting-agent (финансовый субагент).\n"
        "Файлы: documents/finance/, finance/, documents/grants/.\n"
        "Скилл: accounting-agent (RATES.md, CALENDAR.md, CHECKLIST.md).\n"
        "Язык: русский. Проверяй суммы через первоисточники.\n"
    ),
    "legal": (
        "Контекст: legal-agent (юридический субагент).\n"
        "Файлы: documents/contracts/, legal/, DATA/Договоры/.\n"
        "Каждый вывод привязан конкретно к пунктам документов.\n"
        "Нормы законодательства верифицировать через веб-поиск.\n"
    ),
    "operations": (
        "Контекст: operations-agent (операционный субагент).\n"
        "Файлы: operations/, documents/grants/.\n"
        "Память: obligations, status_change, risk.\n"
        "Отслеживай обязательства и конкретные результаты.\n"
    ),
    "strateg": (
        "Контекст: strategy-agent (анализ решений).\n"
        "Файлы: operations/calibration_log.md, operations/system_evolution.md,\n"
        "  operations/risk_log.md, finance/.\n"
        "Каждая рекомендация = конкретный факт + контекст + альтернатива.\n"
    ),
}

AGENT_KEYWORDS = {
    "accounting": [
        "бухгалт", "расход", "бюджет", "налог", "взнос",
        "смета", "ФНС", "СФР", "finance",
    ],
    "legal": [
        "договор", "NDA", "акт", "юрид", "обязательств",
        "contract", "legal",
    ],
    "operations": [
        "статус", "план", "задач", "дедлайн", "risk",
        "операцион",
    ],
    "strateg": [
        "стратег", "приоритет", "развилк", "рекомендац",
        "анализ вариант",
    ],
}


def match_agent_keyword(description):
    """Определяет тип субагента по описанию задачи."""
    if not description:
        return None
    desc_lower = description.lower()
    for agent, keywords in AGENT_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in desc_lower:
                return agent
    return None


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    agent_type = input_data.get("agent_type", "")
    description = input_data.get("description", "")
    prompt = input_data.get("prompt", "")

    project_root = find_project_root()
    context_parts = []

    # 1. Контекст по типу агента
    matched = None
    if agent_type and agent_type != "dispatcher":
        for key in AGENT_CONTEXT:
            if key.lower() in agent_type.lower():
                matched = key
                break

    if not matched:
        matched = (
            match_agent_keyword(description)
            or match_agent_keyword(prompt)
        )

    if matched and matched in AGENT_CONTEXT:
        context_parts.append(AGENT_CONTEXT[matched])
    elif "general" in AGENT_CONTEXT:
        context_parts.append(AGENT_CONTEXT["general"])

    # 2. Прошлые ошибки (Compound Knowledge Base)
    agent_name = matched or agent_type or "dispatcher"
    errors = get_agent_errors(project_root, agent_name)
    if errors:
        context_parts.append(
            f"Прошлые ошибки этого субагента (не повторяй):\n{errors}"
        )

    if context_parts:
        result = {
            "additionalContext": "\n".join(context_parts),
        }
        print(json.dumps(result, ensure_ascii=False))

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
