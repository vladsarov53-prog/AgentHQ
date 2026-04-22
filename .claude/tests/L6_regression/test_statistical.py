"""
L6: Statistical Regression Framework.
Определяет baseline метрики и threshold alerts.
Multi-trial evaluation (N=5) с aggregation.

Источник: Google DeepMind (Scaling Agent Systems),
Anthropic (Grade outputs not paths).
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    THRESHOLDS, REGRESSION_TRIALS, BASELINE_PATH,
)


# === Baseline structure ===
DEFAULT_BASELINE = {
    "version": "1.0",
    "created": datetime.now().isoformat(),
    "updated": datetime.now().isoformat(),
    "metrics": {
        "L0_pass_rate": 1.0,
        "L1_pass_rate": 1.0,
        "L3_pass_rate": 1.0,
        "L5_auto_pass_rate": 1.0,
        "L2_golden_structure_rate": 1.0,
        "anti_hallucination_median": 5.0,
        "source_grounding_median": 4.5,
        "completeness_median": 4.0,
    },
    "per_agent": {
        "accounting": {"pass_rate": 1.0, "hallucination_score": 5.0},
        "legal": {"pass_rate": 1.0, "clause_precision": 5.0},
        "operations": {"pass_rate": 1.0, "deadline_awareness": 5.0},
        "strategy": {"pass_rate": 1.0, "confidence_calibration": 5.0},
    },
    "thresholds": THRESHOLDS,
}


def load_baseline():
    if os.path.isfile(BASELINE_PATH):
        with open(BASELINE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_BASELINE


def save_baseline(baseline):
    os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
    baseline["updated"] = datetime.now().isoformat()
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)


def compare_metrics(baseline_metrics, current_metrics):
    """Compare current metrics against baseline, return alerts."""
    alerts = []
    for key, baseline_val in baseline_metrics.items():
        current_val = current_metrics.get(key, baseline_val)
        delta = current_val - baseline_val

        if "pass_rate" in key:
            if delta < -THRESHOLDS["pass_rate_critical"]:
                alerts.append({
                    "metric": key,
                    "level": "CRITICAL",
                    "baseline": baseline_val,
                    "current": current_val,
                    "delta": delta,
                    "threshold": f"-{THRESHOLDS['pass_rate_critical']*100}%",
                })
            elif delta < -THRESHOLDS["pass_rate_warn"]:
                alerts.append({
                    "metric": key,
                    "level": "WARNING",
                    "baseline": baseline_val,
                    "current": current_val,
                    "delta": delta,
                    "threshold": f"-{THRESHOLDS['pass_rate_warn']*100}%",
                })
        elif "median" in key:
            if delta < -THRESHOLDS["median_score_warn"]:
                alerts.append({
                    "metric": key,
                    "level": "WARNING",
                    "baseline": baseline_val,
                    "current": current_val,
                    "delta": delta,
                    "threshold": f"-{THRESHOLDS['median_score_warn']}",
                })

        # Critical: anti_hallucination below minimum
        if "hallucination" in key and current_val < THRESHOLDS["anti_hallucination_min"]:
            alerts.append({
                "metric": key,
                "level": "CRITICAL",
                "baseline": baseline_val,
                "current": current_val,
                "delta": delta,
                "threshold": f"min={THRESHOLDS['anti_hallucination_min']}",
            })

    return alerts


def run_all():
    print("=== L6: Statistical Regression ===\n")

    baseline = load_baseline()

    print(f"Baseline version: {baseline['version']}")
    print(f"Created: {baseline.get('created', 'N/A')}")
    print(f"Updated: {baseline.get('updated', 'N/A')}")
    print(f"Trials per test: N={REGRESSION_TRIALS}")
    print()

    # Display baseline metrics
    print("### Baseline Metrics\n")
    print("| Metric | Value |")
    print("|--------|-------|")
    for key, val in baseline["metrics"].items():
        print(f"| {key} | {val} |")
    print()

    # Display thresholds
    print("### Regression Thresholds\n")
    print("| Threshold | Value |")
    print("|-----------|-------|")
    for key, val in baseline["thresholds"].items():
        print(f"| {key} | {val} |")
    print()

    # Display per-agent baselines
    print("### Per-Agent Baselines\n")
    print("| Agent | Pass Rate | Special Metric |")
    print("|-------|-----------|----------------|")
    for agent, metrics in baseline["per_agent"].items():
        special = {k: v for k, v in metrics.items() if k != "pass_rate"}
        special_str = ", ".join(f"{k}={v}" for k, v in special.items())
        print(f"| {agent} | {metrics['pass_rate']} | {special_str} |")
    print()

    # Display rubric dimensions
    print("### LLM-as-Judge Рубрика (Universal)\n")
    print("| Dimension | 5 (отлично) | 3 (приемлемо) | 1 (провал) |")
    print("|-----------|-------------|---------------|------------|")
    dimensions = [
        ("completeness", "Все пункты покрыты", "Основные покрыты", "Ключевые пропущены"),
        ("source_grounding", "Каждый факт=файл", "Большинство с источ.", "Без источников"),
        ("anti_hallucination", "0 выдуманных", "0 выдум., маркеры неполн.", "Выдуманный факт"),
        ("format", "Точно по запросу", "Близко к запросу", "Не тот формат"),
        ("reasoning", "Логика безупречна", "Логика корректна", "Логич. ошибки"),
    ]
    for dim, good, ok, bad in dimensions:
        print(f"| {dim} | {good} | {ok} | {bad} |")
    print()

    # Agent-specific dimensions
    print("### Agent-Specific Dimensions\n")
    extras = [
        ("legal", "clause_precision", "Точность ссылок на пункты договора"),
        ("accounting", "arithmetic", "Корректность вычислений"),
        ("strategy", "confidence_calibration", "Адекватность уровней уверенности"),
        ("operations", "deadline_awareness", "Учёт всех дедлайнов"),
    ]
    for agent, dim, desc in extras:
        print(f"  - **{agent}**: +{dim} ({desc})")
    print()

    # Initialize baseline if not exists
    if not os.path.isfile(BASELINE_PATH):
        save_baseline(DEFAULT_BASELINE)
        print(f"Baseline initialized at {BASELINE_PATH}")

    print(f"{'='*50}")
    print("L6 framework ready. Для прогона regression:")
    print(f"  1. Выполнить N={REGRESSION_TRIALS} trials для L2/L3/L4 тестов")
    print("  2. Собрать scores по рубрике (LLM-as-judge)")
    print("  3. Сравнить с baseline: compare_metrics()")
    print("  4. Alerts: pass_rate drop >5% = WARNING, >15% = CRITICAL")
    print(f"{'='*50}")

    return 0


if __name__ == "__main__":
    sys.exit(run_all())
