"""
L2: Runner для golden test cases.
Парсит golden_*.md файлы и генерирует структурированный отчёт.
Интегрируется с pattern_grader для автоматической проверки.

Источник: Anthropic (Eval-Driven), KDD 2025 (pass^k).
"""

import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GOLDEN_TESTS_DIR, AGENT_NAMES


def parse_golden_file(filepath):
    """Parse a golden test markdown file into structured test cases."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    tests = []
    # Split by ## Тест N:
    sections = re.split(r"##\s+Тест\s+\d+:", content)

    for i, section in enumerate(sections[1:], 1):
        test = {"number": i, "file": os.path.basename(filepath)}

        # Extract title (first line)
        lines = section.strip().split("\n")
        test["title"] = lines[0].strip() if lines else f"Test {i}"

        # Extract input
        input_match = re.search(r"\*\*Вход:\*\*\s*(.+?)(?=\n\*\*|\n---|\Z)", section, re.DOTALL)
        test["input"] = input_match.group(1).strip() if input_match else ""

        # Extract expected behavior (both naming variants)
        expected_match = re.search(
            r"\*\*Ожидаем(?:ое поведение|ый результат):\*\*\s*(.+?)(?=\n\*\*|\n---|\Z)",
            section, re.DOTALL
        )
        test["expected"] = expected_match.group(1).strip() if expected_match else ""

        # Extract red flags
        flags_match = re.search(r"\*\*Красные флаги:\*\*\s*(.+?)(?=\n---|\n##|\Z)", section, re.DOTALL)
        test["red_flags"] = flags_match.group(1).strip() if flags_match else ""

        # Extract red flag list items
        test["red_flag_list"] = re.findall(r"[-*]\s+(.+)", test["red_flags"])

        # Extract expected behavior list items
        test["expected_list"] = re.findall(r"[-*]\s+(.+)", test["expected"])

        tests.append(test)

    return tests


def run_all():
    """Parse all golden test files and generate structured report."""
    results = []
    total_tests = 0

    print("=== L2: Golden Test Cases ===\n")

    # Parse all golden files
    if not os.path.isdir(GOLDEN_TESTS_DIR):
        print("FAIL: Golden tests directory not found")
        return 1

    golden_files = sorted([
        f for f in os.listdir(GOLDEN_TESTS_DIR)
        if f.endswith("_golden.md")
    ])

    for gf in golden_files:
        filepath = os.path.join(GOLDEN_TESTS_DIR, gf)
        tests = parse_golden_file(filepath)
        agent_name = gf.replace("_golden.md", "")

        print(f"### {agent_name} ({len(tests)} тестов)\n")

        for test in tests:
            total_tests += 1
            test_id = f"G-{agent_name[:3].upper()}-{test['number']}"

            # Structural validation
            has_input = bool(test["input"])
            has_expected = bool(test["expected_list"])
            has_red_flags = bool(test["red_flag_list"])

            if has_input and has_expected and has_red_flags:
                status = "PASS"
            elif has_input and has_expected:
                status = "WARN"
            else:
                status = "FAIL"

            print(f"  {status}  {test_id} {test['title'][:60]}")
            if test["input"]:
                # Show first line of input
                first_line = test["input"].split("\n")[0][:60]
                print(f"         Вход: \"{first_line}\"")
            print(f"         Ожидание: {len(test['expected_list'])} пунктов")
            print(f"         Red flags: {len(test['red_flag_list'])} паттернов")

            results.append({
                "id": test_id,
                "agent": agent_name,
                "title": test["title"],
                "status": status,
                "input": test["input"],
                "expected_count": len(test["expected_list"]),
                "red_flag_count": len(test["red_flag_list"]),
                "expected_list": test["expected_list"],
                "red_flag_list": test["red_flag_list"],
            })

        print()

    # Summary
    passed = sum(1 for r in results if r["status"] == "PASS")
    warned = sum(1 for r in results if r["status"] == "WARN")
    failed = sum(1 for r in results if r["status"] == "FAIL")

    print(f"{'='*50}")
    print(f"Golden tests: {total_tests} тестов в {len(golden_files)} файлах")
    print(f"Структура: {passed} PASS, {warned} WARN, {failed} FAIL")
    print(f"{'='*50}")

    # Per-agent summary
    print(f"\n| Агент | Тестов | Ожид. пунктов | Red flags |")
    print(f"|-------|--------|---------------|-----------|")
    for gf in golden_files:
        agent = gf.replace("_golden.md", "")
        agent_results = [r for r in results if r["agent"] == agent]
        total_expected = sum(r["expected_count"] for r in agent_results)
        total_flags = sum(r["red_flag_count"] for r in agent_results)
        print(f"| {agent} | {len(agent_results)} | {total_expected} | {total_flags} |")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
