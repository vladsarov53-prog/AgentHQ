"""
Chat Archive Push Hook (Stop)

При завершении каждой Claude Code сессии копирует транскрипт (.jsonl)
в chat-archives/raw/YYYY-MM-DD/<session_id>.jsonl в репо AgentHQ
и пушит в Git, чтобы remote routine могла его заархивировать.

Всегда exit(0) — никогда не блокирует сессию.
"""

import io
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO = r"D:\REDPEAK\Agent systems\AgentHQ"
RAW_DIR = os.path.join(REPO, "chat-archives", "raw")


def _git(args, timeout=30):
    return subprocess.run(
        ["git"] + args,
        cwd=REPO,
        capture_output=True,
        timeout=timeout,
    )


def main():
    try:
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        sys.exit(0)

    transcript_path = data.get("transcript_path", "")
    session_id = data.get("session_id", "unknown")

    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)

    # Проверяем что репо доступен
    if not os.path.isdir(os.path.join(REPO, ".git")):
        print("[chat-archive] repo not found, skipping", file=sys.stderr)
        sys.exit(0)

    # Папка raw по UTC-дате
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest_dir = os.path.join(RAW_DIR, date_str)
    os.makedirs(dest_dir, exist_ok=True)

    # Имя файла — очищаем session_id от спецсимволов
    safe_id = session_id.replace("/", "_").replace("\\", "_").replace(":", "_")[:64]
    dest_file = os.path.join(dest_dir, f"{safe_id}.jsonl")

    try:
        shutil.copy2(transcript_path, dest_file)
    except Exception as e:
        print(f"[chat-archive] copy failed: {e}", file=sys.stderr)
        sys.exit(0)

    # git add
    r = _git(["add", "chat-archives/"], timeout=10)
    if r.returncode != 0:
        print(f"[chat-archive] git add failed: {r.stderr.decode('utf-8', errors='replace')}", file=sys.stderr)
        sys.exit(0)

    # git commit (может быть "nothing to commit" — это нормально)
    r = _git(["commit", "-m", f"chore: chat archive {date_str} [{safe_id[:8]}]"], timeout=15)
    committed = r.returncode == 0

    if committed:
        # git push — не блокируем даже при ошибке
        r = _git(["push", "origin", "master"], timeout=30)
        status = "pushed" if r.returncode == 0 else f"push failed ({r.stderr.decode('utf-8', errors='replace')[:100]})"
    else:
        status = "nothing to commit (already archived)"

    print(f"[chat-archive] {safe_id[:8]} → raw/{date_str}/ | {status}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[chat-archive] unexpected error: {e}", file=sys.stderr)
        sys.exit(0)
