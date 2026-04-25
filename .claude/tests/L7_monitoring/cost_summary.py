"""
Cost Summary CLI
Агрегирует operations/cost_attribution.jsonl по субагентам.

Запуск:
    python .claude/tests/L7_monitoring/cost_summary.py
    python .claude/tests/L7_monitoring/cost_summary.py --days 7
    python .claude/tests/L7_monitoring/cost_summary.py --top 5

Источник: Google DeepMind «Towards a Science of Scaling Agent Systems»
(per-agent token attribution для cost-aware orchestration).
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# Тарифы Anthropic ($/1M токенов) — для оценки стоимости.
# Источник: anthropic.com/pricing (актуально на 2026-04).
# Если модель не известна — используем opus как консервативный максимум.
PRICING = {
    "opus": {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_creation": 18.75},
    "sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_creation": 3.75},
    "haiku": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_creation": 1.0},
}

# Маппинг субагент → модель (из CLAUDE.md)
AGENT_MODELS = {
    "operations-agent": "sonnet",
    "accounting-agent": "sonnet",  # default; opus только для analytics
    "legal-agent": "opus",
    "strategy-agent": "opus",
    "evaluator-agent": "opus",
}


def find_project_root():
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "CLAUDE.md").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent.parent


def load_events(jsonl_path, since_ts=None):
    events = []
    if not jsonl_path.exists():
        return events
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since_ts:
                try:
                    ts = datetime.fromisoformat(event.get("ts", ""))
                    if ts < since_ts:
                        continue
                except (ValueError, TypeError):
                    continue
            events.append(event)
    return events


def estimate_cost_usd(event, model_override=None):
    """Оценивает стоимость события в USD."""
    subagent = event.get("subagent_type", "unknown")
    model = model_override or AGENT_MODELS.get(subagent, "opus")
    rates = PRICING.get(model, PRICING["opus"])

    input_tokens = event.get("input_tokens", 0) or 0
    output_tokens = event.get("output_tokens", 0) or 0
    cache_read = event.get("cache_read_input_tokens", 0) or 0
    cache_creation = event.get("cache_creation_input_tokens", 0) or 0

    cost = (
        (input_tokens / 1_000_000) * rates["input"]
        + (output_tokens / 1_000_000) * rates["output"]
        + (cache_read / 1_000_000) * rates["cache_read"]
        + (cache_creation / 1_000_000) * rates["cache_creation"]
    )
    return cost


def aggregate(events):
    by_agent = defaultdict(lambda: {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read": 0,
        "cache_creation": 0,
        "input_chars": 0,
        "output_chars": 0,
        "cost_usd": 0.0,
        "estimated_count": 0,
        "api_count": 0,
    })

    for ev in events:
        agent = ev.get("subagent_type", "unknown")
        a = by_agent[agent]
        a["calls"] += 1
        a["input_tokens"] += ev.get("input_tokens", 0) or 0
        a["output_tokens"] += ev.get("output_tokens", 0) or 0
        a["cache_read"] += ev.get("cache_read_input_tokens", 0) or 0
        a["cache_creation"] += ev.get("cache_creation_input_tokens", 0) or 0
        a["input_chars"] += ev.get("input_chars", 0) or 0
        a["output_chars"] += ev.get("output_chars", 0) or 0
        a["cost_usd"] += estimate_cost_usd(ev)
        if ev.get("source") == "api":
            a["api_count"] += 1
        else:
            a["estimated_count"] += 1

    return by_agent


def main():
    parser = argparse.ArgumentParser(description="Cost attribution summary")
    parser.add_argument("--days", type=int, default=0,
                        help="Только события за последние N дней (0 = все)")
    parser.add_argument("--top", type=int, default=10,
                        help="Топ N субагентов по стоимости")
    parser.add_argument("--path", type=str, default=None,
                        help="Путь к cost_attribution.jsonl (по умолчанию operations/)")
    args = parser.parse_args()

    project_root = find_project_root()
    jsonl_path = (
        Path(args.path) if args.path
        else project_root / "operations" / "cost_attribution.jsonl"
    )

    since_ts = None
    if args.days > 0:
        since_ts = datetime.now() - timedelta(days=args.days)

    events = load_events(jsonl_path, since_ts=since_ts)

    if not events:
        print(f"\n[INFO] Нет данных в {jsonl_path}")
        if args.days > 0:
            print(f"       (фильтр: последние {args.days} дней)")
        print("\nЕсли cost-attribution хук активен и были вызовы Task — "
              "файл должен заполняться автоматически.")
        sys.exit(0)

    by_agent = aggregate(events)
    sorted_agents = sorted(
        by_agent.items(),
        key=lambda x: x[1]["cost_usd"],
        reverse=True,
    )[:args.top]

    print(f"\n{'='*78}")
    print(f"  Cost Attribution Summary")
    print(f"  Файл: {jsonl_path.name}")
    print(f"  События: {len(events)}")
    if since_ts:
        print(f"  Период: с {since_ts.strftime('%Y-%m-%d')}")
    print(f"{'='*78}\n")

    print(f"  {'Субагент':<22} {'Вызовов':>8} {'Input tok':>11} "
          f"{'Output tok':>11} {'~Cost USD':>10} {'Источник':>14}")
    print(f"  {'-'*22} {'-'*8} {'-'*11} {'-'*11} {'-'*10} {'-'*14}")

    total_cost = 0.0
    total_calls = 0
    total_input = 0
    total_output = 0

    for agent, data in sorted_agents:
        src = (
            f"api:{data['api_count']}/est:{data['estimated_count']}"
            if (data['api_count'] or data['estimated_count']) else "?"
        )
        print(
            f"  {agent[:22]:<22} {data['calls']:>8} "
            f"{data['input_tokens']:>11,} {data['output_tokens']:>11,} "
            f"{data['cost_usd']:>10.4f} {src:>14}"
        )
        total_cost += data["cost_usd"]
        total_calls += data["calls"]
        total_input += data["input_tokens"]
        total_output += data["output_tokens"]

    print(f"  {'-'*22} {'-'*8} {'-'*11} {'-'*11} {'-'*10} {'-'*14}")
    print(
        f"  {'ИТОГО':<22} {total_calls:>8} "
        f"{total_input:>11,} {total_output:>11,} "
        f"{total_cost:>10.4f}"
    )

    print(f"\n[ВНИМАНИЕ] Стоимость оценочная. "
          f"'estimated' — токены оценены по символам (~3.5 char/token).")
    print(f"           Реальные тарифы: см. anthropic.com/pricing")
    print(f"{'='*78}\n")


if __name__ == "__main__":
    main()
