"""
AgentHQ Test Runner - Единый раннер всех уровней тестирования.

Режимы запуска:
  --quick     L0 + L1         (< 2 мин, перед каждым изменением)
  --standard  L0 + L1 + L3    (< 5 мин, перед коммитом)
  --full      L0-L5           (< 15 мин, перед релизом)
  --regression L0-L7          (полный прогон)
  --monitor   L7 только       (on demand)

Источники: Anthropic (Eval-Driven), Google DeepMind (Scaling),
LangChain/LangSmith (CI/CD threshold gating).
"""

import argparse
import importlib
import importlib.util
import os
import sys
import time
from datetime import datetime

# Ensure tests directory is in path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)

from config import PROJECT_ROOT, OPERATIONS_DIR, REPORTS_DIR


def run_level(level_name, module_path, description):
    """Run a test level via subprocess for isolation."""
    print(f"\n{'='*60}")
    print(f"  {level_name}: {description}")
    print(f"{'='*60}\n")

    start = time.time()
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, module_path],
            capture_output=False,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
            encoding="utf-8",
            errors="replace",
        )
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT running {level_name}")
        exit_code = 1
    except Exception as e:
        print(f"  ERROR running {level_name}: {e}")
        exit_code = 1

    elapsed = time.time() - start
    status = "PASS" if exit_code == 0 else "FAIL"
    return {
        "level": level_name,
        "description": description,
        "status": status,
        "exit_code": exit_code,
        "elapsed": elapsed,
    }


def generate_report(results, mode):
    """Generate markdown report."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    report = []
    report.append(f"# Test Results {date_str}\n")
    report.append(f"**Время:** {time_str}")
    report.append(f"**Режим:** {mode}")
    report.append(f"**Методология:** Anthropic (Eval-Driven) + Google DeepMind (Scaling) + Microsoft AgentRx + LangChain\n")
    report.append("")

    # Summary table
    report.append("## Сводка\n")
    report.append("| Уровень | Описание | Статус | Время |")
    report.append("|---------|----------|--------|-------|")

    total_pass = 0
    total_fail = 0
    total_time = 0

    for r in results:
        status_icon = "PASS" if r["status"] == "PASS" else "FAIL"
        elapsed = f"{r['elapsed']:.1f}s"
        report.append(f"| {r['level']} | {r['description']} | {status_icon} | {elapsed} |")
        if r["status"] == "PASS":
            total_pass += 1
        else:
            total_fail += 1
        total_time += r["elapsed"]

    total = total_pass + total_fail
    rate = f"{total_pass/total*100:.1f}%" if total > 0 else "N/A"
    report.append(f"| **ИТОГО** | **{total} уровней** | **{rate}** | **{total_time:.1f}s** |")
    report.append("")

    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="AgentHQ Test Runner")
    parser.add_argument("--quick", action="store_true", help="L0+L1 (fast)")
    parser.add_argument("--standard", action="store_true", help="L0+L1+L3 (pre-commit)")
    parser.add_argument("--full", action="store_true", help="L0-L5 (pre-release)")
    parser.add_argument("--regression", action="store_true", help="L0-L7 (weekly)")
    parser.add_argument("--monitor", action="store_true", help="L7 only")
    parser.add_argument("--level", type=str, help="Run specific level (e.g. L0, L1)")
    parser.add_argument("--report", action="store_true", help="Save report to file")
    args = parser.parse_args()

    # Default to --quick if no mode specified
    if not any([args.quick, args.standard, args.full, args.regression, args.monitor, args.level]):
        args.quick = True

    # Define test levels
    levels = {
        "L0-prompts": (
            os.path.join(TESTS_DIR, "L0_static", "test_prompts.py"),
            "Статический анализ промптов"
        ),
        "L0-files": (
            os.path.join(TESTS_DIR, "L0_static", "test_files.py"),
            "Целостность файлов"
        ),
        "L1": (
            os.path.join(TESTS_DIR, "L1_unit", "test_hooks.py"),
            "Unit-тесты хуков (85 тестов)"
        ),
        "L2": (
            os.path.join(TESTS_DIR, "L2_golden", "test_golden_runner.py"),
            "Golden test cases (структура)"
        ),
        "L3": (
            os.path.join(TESTS_DIR, "L3_routing", "test_routing.py"),
            "Маршрутизация (30 кейсов)"
        ),
        "L4": (
            os.path.join(TESTS_DIR, "L4_integration", "test_workflows.py"),
            "Integration & E2E (golden reference)"
        ),
        "L5": (
            os.path.join(TESTS_DIR, "L5_adversarial", "test_adversarial.py"),
            "Adversarial тесты (20 кейсов)"
        ),
        "L6": (
            os.path.join(TESTS_DIR, "L6_regression", "test_statistical.py"),
            "Statistical regression framework"
        ),
        "L7": (
            os.path.join(TESTS_DIR, "L7_monitoring", "analyze_calibration.py"),
            "Production monitoring"
        ),
    }

    # Select levels based on mode
    if args.level:
        selected = [k for k in levels if k.startswith(args.level)]
    elif args.monitor:
        selected = ["L7"]
    elif args.quick:
        selected = ["L0-prompts", "L0-files", "L1"]
    elif args.standard:
        selected = ["L0-prompts", "L0-files", "L1", "L3"]
    elif args.full:
        selected = ["L0-prompts", "L0-files", "L1", "L2", "L3", "L4", "L5"]
    elif args.regression:
        selected = list(levels.keys())
    else:
        selected = ["L0-prompts", "L0-files", "L1"]

    mode = (
        "quick" if args.quick else
        "standard" if args.standard else
        "full" if args.full else
        "regression" if args.regression else
        "monitor" if args.monitor else
        f"level:{args.level}" if args.level else
        "quick"
    )

    print(f"\n{'#'*60}")
    print(f"  AgentHQ Test Runner")
    print(f"  Mode: {mode} | Levels: {len(selected)}")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")

    os.chdir(PROJECT_ROOT)

    # Run selected levels
    results = []
    for level_name in selected:
        if level_name in levels:
            path, desc = levels[level_name]
            if os.path.isfile(path):
                result = run_level(level_name, path, desc)
                results.append(result)
            else:
                print(f"\n  SKIP  {level_name}: file not found ({path})")

    # Final summary
    print(f"\n\n{'#'*60}")
    print(f"  FINAL SUMMARY")
    print(f"{'#'*60}\n")

    total_pass = sum(1 for r in results if r["status"] == "PASS")
    total_fail = sum(1 for r in results if r["status"] == "FAIL")
    total_time = sum(r["elapsed"] for r in results)

    for r in results:
        icon = "PASS" if r["status"] == "PASS" else "FAIL"
        print(f"  {icon}  {r['level']}: {r['description']} ({r['elapsed']:.1f}s)")

    total = total_pass + total_fail
    rate = f"{total_pass/total*100:.1f}%" if total > 0 else "N/A"
    print(f"\n  Total: {total_pass}/{total} levels PASS ({rate}), {total_time:.1f}s")

    if total_fail > 0:
        print(f"\n  {total_fail} LEVEL(S) FAILED")
    else:
        print(f"\n  ALL LEVELS PASSED")

    # Save report
    if args.report:
        report = generate_report(results, mode)
        os.makedirs(REPORTS_DIR, exist_ok=True)
        report_path = os.path.join(
            REPORTS_DIR,
            f"test_results_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n  Report saved: {report_path}")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
