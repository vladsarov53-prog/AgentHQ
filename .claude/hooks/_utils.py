"""
Shared utilities for AgentHQ hooks.
"""

import subprocess
from pathlib import Path


def find_project_root():
    """Ищет корень проекта по наличию CLAUDE.md или .git."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "CLAUDE.md").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent


def get_git_log(project_root, count=10):
    """Возвращает последние N записей git log."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{count}"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            cwd=str(project_root),
        )
        if result.returncode != 0:
            return ""
        lines = result.stdout.strip().split("\n")
        return "\n".join(lines)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def get_session_log_entries(project_root, count=15):
    """Читает последние записи из SESSION_LOG.md."""
    log_path = project_root / "SESSION_LOG.md"
    if not log_path.exists():
        return ""
    try:
        content = log_path.read_text(encoding="utf-8").strip()
        recent = [line for line in content.split("\n") if line.startswith("- [")]
        return "\n".join(recent[-count:])
    except OSError:
        return ""


def get_calibration_entries(project_root, count=10):
    """Читает последние записи из operations/calibration_log.md."""
    cal_path = project_root / "operations" / "calibration_log.md"
    if not cal_path.exists():
        return ""
    try:
        content = cal_path.read_text(encoding="utf-8").strip()
        table_lines = []
        entries = []
        for line in content.split("\n"):
            if "|---" in line:
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 5:
                entries.append(line)
        return "\n".join(entries[-count:])
    except OSError:
        return ""
