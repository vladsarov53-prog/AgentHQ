"""
Конфигурация тестовой инфраструктуры AgentHQ.
Пути, пороги, константы для всех уровней тестирования.

Источники: Anthropic (Eval-Driven Development), Google DeepMind (Scaling Agent Systems).
"""

import os

# === Пути ===
PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
HOOKS_DIR = os.path.join(PROJECT_ROOT, ".claude", "hooks")
AGENTS_DIR = os.path.join(PROJECT_ROOT, ".claude", "agents")
SKILLS_DIR = os.path.join(PROJECT_ROOT, ".claude", "skills")
TESTS_DIR = os.path.join(PROJECT_ROOT, ".claude", "tests")
GOLDEN_TESTS_DIR = os.path.join(AGENTS_DIR, "tests")
BACKUPS_DIR = os.path.join(AGENTS_DIR, "backups")
OPERATIONS_DIR = os.path.join(PROJECT_ROOT, "operations")
REPORTS_DIR = os.path.join(TESTS_DIR, "reports")
SETTINGS_PATH = os.path.join(PROJECT_ROOT, ".claude", "settings.json")
CLAUDE_MD_PATH = os.path.join(PROJECT_ROOT, "CLAUDE.md")

# === Пороги (по Google DeepMind regression thresholds) ===
THRESHOLDS = {
    "pass_rate_warn": 0.05,       # > 5% drop = WARNING
    "pass_rate_critical": 0.15,   # > 15% drop = CRITICAL
    "median_score_warn": 0.5,     # > 0.5 drop = WARNING
    "latency_warn": 0.20,         # > 20% increase = WARNING
    "anti_hallucination_min": 4,  # < 4 in ANY trial = CRITICAL
    "marker_overload": 3,         # >= 3 markers = stopping condition
    "file_access_limit": 5,       # > 5 accesses = STOP
}

# === Agents ===
AGENT_NAMES = ["accounting-agent", "legal-agent", "operations-agent", "strategy-agent"]
AGENT_FILES = {name: os.path.join(AGENTS_DIR, f"{name}.md") for name in AGENT_NAMES}

# === Обязательные секции в промптах агентов ===
REQUIRED_AGENT_SECTIONS = [
    "Reflection",
    "Context Engineering",
    "Stopping",
    "источник",  # anti-hallucination: source requirement
]

# === Маркеры неуверенности ===
UNCERTAINTY_MARKERS = [
    "[ТРЕБУЕТ ПРОВЕРКИ]",
    "[ПРОВЕРИТЬ НОРМУ]",
    "[ПРИБЛИЗИТЕЛЬНО]",
    "[ДАННЫЕ ОТСУТСТВУЮТ]",
    "[МОЯ ИНТЕРПРЕТАЦИЯ]",
]

# === Red flag слова (не должны быть в промптах агентов) ===
PROMPT_RED_FLAGS = [
    r"\bвероятно\b",
    r"\bнаверное\b",
    r"\bshould work\b",
    r"\bprobably\b",
    r"\bseems to\b",
]

# === Hooks ===
EXPECTED_HOOKS = {
    "PreToolUse": ["safety-guard.py"],
    "PostToolUse": [
        "session-log.py",
        "lint-check.py",
        "agent-test-trigger.py",
        "cost-attribution.py",
        "memory-index.py",
        "agent-trace.py",
    ],
    "SessionStart": [
        "vault-context.py",
        "context-recovery.py",
        "mcp-health-check.py",
    ],
    "Stop": ["verification-gate.py"],
    "SubagentStart": ["subagent-context.py"],
    "UserPromptSubmit": ["prompt-enricher.py", "planning-prompt.py"],
}

# === LLM-as-judge рубрика (Anthropic eval-driven) ===
UNIVERSAL_RUBRIC = {
    "completeness": {
        5: "Все пункты покрыты, дополнительные инсайты",
        3: "Основные пункты покрыты",
        1: "Пропущены ключевые пункты",
    },
    "source_grounding": {
        5: "Каждый факт = файл:строка или memory ID",
        3: "Большинство фактов с источниками",
        1: "Факты без источников",
    },
    "anti_hallucination": {
        5: "0 выдуманных фактов, корректные маркеры",
        3: "0 выдуманных, но маркеры неполные",
        1: "Выдуманный факт/номер/дата",
    },
    "format": {
        5: "Точно по запросу",
        3: "Близко к запросу",
        1: "Не тот формат",
    },
    "reasoning": {
        5: "Логика безупречна, рекомендация обоснована",
        3: "Логика корректна",
        1: "Логические ошибки",
    },
}

# === Statistical regression ===
REGRESSION_TRIALS = 5
BASELINE_PATH = os.path.join(TESTS_DIR, "L6_regression", "baseline.json")

# === Calibration log ===
CALIBRATION_LOG_PATH = os.path.join(OPERATIONS_DIR, "calibration_log.md")
SYSTEM_EVOLUTION_PATH = os.path.join(OPERATIONS_DIR, "system_evolution.md")

# === Категории ошибок (Microsoft AgentRx) ===
ERROR_CATEGORIES = [
    "missed_data",
    "hallucination",
    "wrong_format",
    "wrong_tone",
    "slow",
    "overkill",
    "reasoning_error",
    "incomplete_task",
    "context_missing",
]
