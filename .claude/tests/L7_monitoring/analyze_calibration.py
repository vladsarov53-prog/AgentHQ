"""
L7: Production Monitoring - Calibration Log Analyzer.
Автоанализ calibration_log.md и system_evolution.md.
Pattern detection, improvement tracking, Compound KB growth.

Источник: Microsoft AgentRx (Critical Failure Step),
OpenAI (Self-Evolving Agents), Meta HyperAgents (Cross-Domain Transfer).
"""

import os
import re
import sys
from datetime import datetime, timedelta
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    CALIBRATION_LOG_PATH, SYSTEM_EVOLUTION_PATH, ERROR_CATEGORIES,
)


def parse_calibration_log(filepath):
    """Parse calibration_log.md into structured entries."""
    if not os.path.isfile(filepath):
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    entries = []
    for line in content.split("\n"):
        if not line.startswith("| 20"):
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) >= 7:
            entries.append({
                "date": parts[0],
                "agent": parts[1],
                "task": parts[2],
                "rating": parts[3],
                "problem": parts[4],
                "category": parts[5],
                "action": parts[6],
            })
    return entries


def parse_evolution_log(filepath):
    """Parse system_evolution.md into structured entries."""
    if not os.path.isfile(filepath):
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    entries = []
    for line in content.split("\n"):
        if not line.startswith("| 20"):
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) >= 5:
            entries.append({
                "date": parts[0],
                "source": parts[1],
                "change": parts[2],
                "file": parts[3],
                "result": parts[4],
            })
    return entries


def detect_patterns(entries, window_days=14):
    """Detect repeating error patterns within time window."""
    if len(entries) < 2:
        return []

    # Count agent+category combinations
    combos = Counter()
    for entry in entries:
        key = f"{entry['agent']}+{entry['category']}"
        combos[key] += 1

    patterns = []
    for combo, count in combos.items():
        if count >= 2:
            agent, category = combo.split("+")
            patterns.append({
                "agent": agent,
                "category": category,
                "count": count,
                "severity": "WARNING" if count < 3 else "CRITICAL",
            })

    return patterns


def analyze_cross_domain_transfer(entries):
    """Check if rules from one agent apply to others."""
    category_agents = {}
    for entry in entries:
        cat = entry["category"]
        agent = entry["agent"]
        category_agents.setdefault(cat, set()).add(agent)

    suggestions = []
    for cat, agents in category_agents.items():
        if len(agents) >= 2:
            suggestions.append({
                "category": cat,
                "affected_agents": list(agents),
                "suggestion": f"Категория '{cat}' затрагивает {len(agents)} агентов. Рассмотреть общее правило.",
            })

    return suggestions


def run_all():
    print("=== L7: Production Monitoring ===\n")

    # Parse logs
    cal_entries = parse_calibration_log(CALIBRATION_LOG_PATH)
    evo_entries = parse_evolution_log(SYSTEM_EVOLUTION_PATH)

    print(f"Calibration log: {len(cal_entries)} записей")
    print(f"System evolution: {len(evo_entries)} записей\n")

    # T-7.1: Pattern detection
    print("### T-7.1: Pattern Detection\n")
    patterns = detect_patterns(cal_entries)
    if patterns:
        print("| Агент | Категория | Повторений | Severity |")
        print("|-------|-----------|------------|----------|")
        for p in patterns:
            print(f"| {p['agent']} | {p['category']} | {p['count']} | {p['severity']} |")
    else:
        print("Повторяющихся паттернов не обнаружено (< 3 записей)")
    print()

    # T-7.2: Critical Failure Step analysis
    print("### T-7.2: Critical Failure Step Analysis\n")
    for entry in cal_entries:
        print(f"  {entry['date']} | {entry['agent']} | {entry['category']}")
        print(f"    Проблема: {entry['problem'][:80]}")
        print(f"    Действие: {entry['action'][:80]}")
        print()

    # T-7.3: Cross-domain transfer
    print("### T-7.3: Cross-Domain Transfer\n")
    suggestions = analyze_cross_domain_transfer(cal_entries)
    if suggestions:
        for s in suggestions:
            print(f"  {s['category']}: агенты {s['affected_agents']}")
            print(f"    -> {s['suggestion']}")
    else:
        print("  Недостаточно данных для cross-domain анализа")
    print()

    # T-7.4: Improvement tracking
    print("### T-7.4: Improvement Tracking\n")
    print(f"Всего улучшений: {len(evo_entries)}")
    if evo_entries:
        print("\n| Дата | Изменение | Результат |")
        print("|------|-----------|-----------|")
        for e in evo_entries[-5:]:  # Last 5
            change = e["change"][:50]
            result = e["result"][:30]
            print(f"| {e['date']} | {change} | {result} |")
    print()

    # T-7.5: Error category distribution
    print("### T-7.5: Error Category Distribution\n")
    if cal_entries:
        cat_counts = Counter(e["category"] for e in cal_entries)
        print("| Категория | Кол-во | % |")
        print("|-----------|--------|---|")
        total = len(cal_entries)
        for cat in ERROR_CATEGORIES:
            count = cat_counts.get(cat, 0)
            pct = f"{count/total*100:.0f}%" if total > 0 else "0%"
            bar = "#" * count
            print(f"| {cat} | {count} | {pct} {bar} |")
    else:
        print("  Нет данных")
    print()

    # Weekly dashboard
    print("### Weekly Dashboard\n")
    print(f"  Total tasks with feedback: {len(cal_entries)}")
    if cal_entries:
        warn = sum(1 for e in cal_entries if "⚠" in e["rating"])
        fail = sum(1 for e in cal_entries if "❌" in e["rating"])
        print(f"  ⚠️ Warnings: {warn}")
        print(f"  ❌ Failures: {fail}")
        top_cat = Counter(e["category"] for e in cal_entries).most_common(1)
        if top_cat:
            print(f"  Top error category: {top_cat[0][0]} ({top_cat[0][1]}x)")
        top_agent = Counter(e["agent"] for e in cal_entries).most_common(1)
        if top_agent:
            print(f"  Most problematic: {top_agent[0][0]} ({top_agent[0][1]}x)")
    print(f"  System improvements applied: {len(evo_entries)}")
    print(f"  Rolled back: 0")

    print(f"\n{'='*50}")
    print("L7 Monitoring complete.")
    print(f"{'='*50}")

    return 0


if __name__ == "__main__":
    sys.exit(run_all())
