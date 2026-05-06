"""
Pattern Grader: проверка ответов агентов по regex-паттернам.
Используется для golden tests (L2) и adversarial tests (L5).

Источник: Anthropic (Eval-Driven Development - rubric grading).
"""

import re
from typing import List, Dict, Optional


class PatternGradeResult:
    def __init__(self):
        self.checks = []
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def add_check(self, name: str, status: str, detail: str = ""):
        self.checks.append({"name": name, "status": status, "detail": detail})
        if status == "PASS":
            self.passed += 1
        elif status == "FAIL":
            self.failed += 1
        elif status == "WARN":
            self.warnings += 1

    @property
    def overall(self) -> str:
        if self.failed > 0:
            return "FAIL"
        if self.warnings > 0:
            return "WARN"
        return "PASS"

    def summary(self) -> str:
        return f"{self.passed} PASS, {self.warnings} WARN, {self.failed} FAIL"


def grade_response(
    response: str,
    required_patterns: Optional[List[str]] = None,
    forbidden_patterns: Optional[List[str]] = None,
    required_markers: Optional[List[str]] = None,
    has_table: bool = False,
    has_source: bool = False,
    min_length: int = 0,
    max_red_flags: int = 0,
) -> PatternGradeResult:
    """
    Grade an agent response against pattern rules.

    Args:
        response: The agent's response text
        required_patterns: Regex patterns that MUST be present
        forbidden_patterns: Regex patterns that MUST NOT be present (red flags)
        required_markers: Uncertainty markers that should be present
        has_table: Whether response should contain a markdown table
        has_source: Whether response should contain source references
        min_length: Minimum response length
        max_red_flags: Maximum allowed red flag matches (0 = none allowed)
    """
    result = PatternGradeResult()

    # Length check
    if min_length > 0:
        if len(response) >= min_length:
            result.add_check("min_length", "PASS", f"{len(response)} >= {min_length}")
        else:
            result.add_check("min_length", "FAIL", f"{len(response)} < {min_length}")

    # Required patterns
    if required_patterns:
        for pattern in required_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                result.add_check(f"required: {pattern[:30]}", "PASS")
            else:
                result.add_check(f"required: {pattern[:30]}", "FAIL", "not found")

    # Forbidden patterns (red flags)
    if forbidden_patterns:
        total_matches = 0
        for pattern in forbidden_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            if matches:
                total_matches += len(matches)
                if total_matches > max_red_flags:
                    result.add_check(f"forbidden: {pattern[:30]}", "FAIL", f"found: {matches[:3]}")
                else:
                    result.add_check(f"forbidden: {pattern[:30]}", "WARN", f"found: {matches[:3]}")
            else:
                result.add_check(f"forbidden: {pattern[:30]}", "PASS")

    # Required markers
    if required_markers:
        for marker in required_markers:
            if marker in response:
                result.add_check(f"marker: {marker}", "PASS")
            else:
                result.add_check(f"marker: {marker}", "WARN", "not found")

    # Table check
    if has_table:
        if re.search(r"\|.*\|.*\|", response):
            result.add_check("has_table", "PASS")
        else:
            result.add_check("has_table", "FAIL", "no markdown table found")

    # Source reference check
    if has_source:
        source_patterns = [
            r"источник:", r"файл[:\s]",
            r"[\w/]+\.(?:md|pdf|docx|xlsx|json)",
            r"DATA/", r"operations/", r"documents/",
            r"\.claude/skills/", r"memory/",
            r"RATES\.md", r"CALENDAR\.md",
        ]
        has_any_source = any(
            re.search(p, response, re.IGNORECASE) for p in source_patterns
        )
        if has_any_source:
            result.add_check("has_source", "PASS")
        else:
            result.add_check("has_source", "FAIL", "no source reference found")

    return result


# === Pre-built grading profiles ===

TONE_RED_FLAGS_TEAM = [
    r"\u2014",                        # длинное тире
    r"[Вв]\s+рамках\b",              # канцелярит
    r"[Оо]существить\b",
    r"[Оо]беспечить\s+реализацию",
    r"[Хх]очется\s+отметить",
    r"[Сс]ледует\s+подчеркнуть",
    r"[Нн]еобходимо\s+учитывать",
]

TONE_RED_FLAGS_FORMAL = [
    r"\b(?:ладно|ок|ага|ну)\b",
    r"(?:!{2,})",
    r"\b(?:прикольно|круто|супер)\b",
]

HALLUCINATION_RED_FLAGS = [
    r"ГОСТ\s+\d+[-\.]\d+",           # ГОСТ без проверки
    r"[Сс]татья\s+\d+\s+[А-Я]",     # статья закона
    r"патент\s+(?:№|номер)\s*\d+",   # номер патента
]

SOURCE_PATTERNS_REQUIRED = [
    r"(?:источник|файл|из)\s*:?\s*[\w/]+\.\w+",
    r"(?:DATA|operations|documents|finance|memory)/",
]


def grade_accounting_response(response: str) -> PatternGradeResult:
    """Grade accounting agent response."""
    return grade_response(
        response,
        required_patterns=[r"\d+[\s\xa0]?\d*\s*(?:руб|₽|%)"],
        forbidden_patterns=HALLUCINATION_RED_FLAGS,
        has_source=True,
        min_length=100,
    )


def grade_legal_response(response: str) -> PatternGradeResult:
    """Grade legal agent response."""
    return grade_response(
        response,
        required_patterns=[r"п\.\s*\d+\.?\d*"],  # пункт договора
        forbidden_patterns=HALLUCINATION_RED_FLAGS,
        has_table=True,
        has_source=True,
        min_length=200,
    )


def grade_tone_team(response: str) -> PatternGradeResult:
    """Grade tone for team communication."""
    return grade_response(
        response,
        forbidden_patterns=TONE_RED_FLAGS_TEAM,
        max_red_flags=0,
    )


def grade_tone_formal(response: str) -> PatternGradeResult:
    """Grade tone for FSI/Skolkovo communication."""
    return grade_response(
        response,
        forbidden_patterns=TONE_RED_FLAGS_FORMAL,
        max_red_flags=0,
    )
