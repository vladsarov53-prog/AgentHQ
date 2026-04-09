"""
Vault Context Hook (SessionStart)
Загружает ключевой контекст проекта при старте сессии.

Реализует протокол холодного старта из CLAUDE.md:
паттерны ошибок, открытые риски, структура DATA/.

Источник: Anthropic (SessionStart hooks), CLAUDE.md (Cold Start Protocol).
"""

import json
import sys
from pathlib import Path
from datetime import datetime

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


def load_calibration_patterns(project_root):
    """Проверяет calibration_log.md на повторяющиеся проблемы (2+ раза)."""
    cal_path = project_root / "operations" / "calibration_log.md"
    if not cal_path.exists():
        return ""
    try:
        content = cal_path.read_text(encoding="utf-8").strip()
        errors = {}
        for line in content.split("\n"):
            if "|---" in line or not line.strip().startswith("|"):
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 5:
                agent = parts[1] if len(parts) > 1 else ""
                category = parts[3] if len(parts) > 3 else ""
                key = f"{agent}:{category}"
                errors[key] = errors.get(key, 0) + 1

        patterns = []
        for key, count in errors.items():
            if count >= 2:
                agent, category = key.split(":", 1)
                patterns.append(
                    f"  - {agent}: {category} ({count} случаев)"
                )

        if patterns:
            return "Паттерны ошибок:\n" + "\n".join(patterns)
        return ""
    except (OSError, ValueError):
        return ""


def load_risk_summary(project_root):
    """Загружает краткую сводку открытых рисков."""
    risk_path = project_root / "operations" / "risk_log.md"
    if not risk_path.exists():
        return ""
    try:
        content = risk_path.read_text(encoding="utf-8").strip()
        risks = []
        for line in content.split("\n"):
            stripped = line.strip()
            # Пропускаем заголовки, разделители и шаблонные строки
            if not stripped or not stripped.startswith("|"):
                continue
            if "|---" in stripped:
                continue
            lower = stripped.lower()
            # Пропускаем шаблонные строки-подсказки
            if "низк/средн/высок" in lower:
                continue
            if "дата выявления" in lower or "№" in lower:
                continue
            # Ищем реальные записи с активными рисками
            if any(
                m in lower
                for m in [
                    "высокий", "критический", "high",
                    "critical", "открыт", "active",
                ]
            ):
                # Извлекаем описание риска (3-й столбец)
                parts = [p.strip() for p in stripped.split("|") if p.strip()]
                if len(parts) >= 3:
                    risks.append(parts[2])
        if risks:
            return "Открытые риски: " + "; ".join(risks[:3])
        return ""
    except OSError:
        return ""


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        input_data = {}

    project_root = find_project_root()
    context_parts = []

    # 1. Паттерны ошибок из calibration_log
    patterns = load_calibration_patterns(project_root)
    if patterns:
        context_parts.append(patterns)

    # 2. Открытые риски
    risks = load_risk_summary(project_root)
    if risks:
        context_parts.append(risks)

    # 3. Структура DATA/
    data_path = project_root / "DATA"
    if data_path.exists():
        try:
            data_dirs = sorted(
                [d.name for d in data_path.iterdir() if d.is_dir()]
            )
            if data_dirs:
                listing = ", ".join(data_dirs[:12])
                context_parts.append(
                    f"DATA/ ({len(data_dirs)} папок): {listing}"
                )
        except OSError:
            pass

    # 4. Дата для контекста
    context_parts.append(
        f"Дата: {datetime.now().strftime('%Y-%m-%d')}"
    )

    if context_parts:
        result = {
            "additionalContext": (
                "Контекст сессии:\n" + "\n".join(context_parts)
            ),
        }
        print(json.dumps(result, ensure_ascii=False))

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
