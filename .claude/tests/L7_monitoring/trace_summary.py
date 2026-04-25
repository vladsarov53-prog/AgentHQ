"""
Trace Summary CLI
Агрегирует operations/agent_traces.jsonl по типам инструментов.

Запуск:
    python .claude/tests/L7_monitoring/trace_summary.py
    python .claude/tests/L7_monitoring/trace_summary.py --days 1
    python .claude/tests/L7_monitoring/trace_summary.py --tool Task
    python .claude/tests/L7_monitoring/trace_summary.py --errors-only

Источник: Google SRE Workbook (post-hoc trace analysis),
Anthropic «Building Effective Agents» (observability).
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
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since_ts:
                try:
                    ts = datetime.fromisoformat(ev.get("ts", ""))
                    if ts < since_ts:
                        continue
                except (ValueError, TypeError):
                    continue
            events.append(ev)
    return events


def main():
    parser = argparse.ArgumentParser(description="Agent traces summary")
    parser.add_argument("--days", type=int, default=0,
                        help="Только за последние N дней (0 = все)")
    parser.add_argument("--tool", type=str, default=None,
                        help="Фильтр по типу инструмента (Bash, Task, ...)")
    parser.add_argument("--errors-only", action="store_true",
                        help="Только события с has_error=true")
    parser.add_argument("--top", type=int, default=10,
                        help="Топ N инструментов")
    parser.add_argument("--path", type=str, default=None)
    args = parser.parse_args()

    project_root = find_project_root()
    jsonl_path = (
        Path(args.path) if args.path
        else project_root / "operations" / "agent_traces.jsonl"
    )

    since_ts = None
    if args.days > 0:
        since_ts = datetime.now() - timedelta(days=args.days)

    events = load_events(jsonl_path, since_ts=since_ts)
    if not events:
        print(f"\n[INFO] Нет данных в {jsonl_path}")
        sys.exit(0)

    if args.tool:
        events = [e for e in events if e.get("tool_name") == args.tool]
    if args.errors_only:
        events = [e for e in events if e.get("has_error")]

    # Агрегация по tool_name
    by_tool = defaultdict(lambda: {
        "calls": 0, "errors": 0,
        "total_output_chars": 0,
        "subagents": defaultdict(int),
    })
    for ev in events:
        t = ev.get("tool_name", "?")
        a = by_tool[t]
        a["calls"] += 1
        if ev.get("has_error"):
            a["errors"] += 1
        a["total_output_chars"] += ev.get("output_size_chars", 0) or 0
        if ev.get("subagent_type"):
            a["subagents"][ev["subagent_type"]] += 1

    sorted_tools = sorted(
        by_tool.items(),
        key=lambda x: x[1]["calls"],
        reverse=True,
    )[:args.top]

    print(f"\n{'='*78}")
    print(f"  Agent Traces Summary")
    print(f"  Файл: {jsonl_path.name}")
    print(f"  Событий: {len(events)}")
    if since_ts:
        print(f"  Период: с {since_ts.strftime('%Y-%m-%d')}")
    if args.tool:
        print(f"  Фильтр инструмента: {args.tool}")
    if args.errors_only:
        print(f"  Только ошибки")
    print(f"{'='*78}\n")

    print(f"  {'Tool':<20} {'Calls':>7} {'Errors':>7} {'Err %':>7} {'Avg out':>9}")
    print(f"  {'-'*20} {'-'*7} {'-'*7} {'-'*7} {'-'*9}")

    total_calls = 0
    total_errors = 0
    for tool, data in sorted_tools:
        avg_out = (
            data["total_output_chars"] // data["calls"]
            if data["calls"] else 0
        )
        err_pct = (
            data["errors"] / data["calls"] * 100
            if data["calls"] else 0
        )
        marker = " !" if err_pct > 10 else ""
        print(
            f"  {tool[:20]:<20} {data['calls']:>7} {data['errors']:>7} "
            f"{err_pct:>6.1f}% {avg_out:>9,}{marker}"
        )
        total_calls += data["calls"]
        total_errors += data["errors"]
        # Если Task — показать разбивку по субагентам
        if tool == "Task" and data["subagents"]:
            for sa, cnt in sorted(data["subagents"].items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"    └─ {sa}: {cnt}")

    print(f"  {'-'*20} {'-'*7} {'-'*7} {'-'*7} {'-'*9}")
    overall_err_pct = (total_errors / total_calls * 100) if total_calls else 0
    print(
        f"  {'TOTAL':<20} {total_calls:>7} {total_errors:>7} "
        f"{overall_err_pct:>6.1f}%"
    )

    # Если errors-only — показать примеры
    if args.errors_only and events:
        print(f"\n  Последние 5 ошибок:")
        for ev in events[-5:]:
            print(f"  [{ev.get('ts', '?')}] {ev.get('tool_name', '?')}")
            preview = ev.get("input_preview", "")[:100]
            print(f"    input: {preview}")

    print(f"\n{'='*78}\n")


if __name__ == "__main__":
    main()
