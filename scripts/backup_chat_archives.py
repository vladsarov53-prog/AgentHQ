#!/usr/bin/env python3
"""
Daily backup script for RedPeak HQ (AgentHQ).
Запускается remote-routine в 19:00 МСК:
  1. git-tag snapshot master
  2. Архивация chat-archives/raw/ → .tar.gz (gzip level 9)
  3. Очистка tar.gz старше 90 дней
  4. Обновление chat-archives/index.md + backups/log.md + backups/manifest-DATE.md
  5. git commit + push
"""

import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Корень репо — скрипт лежит в scripts/, поднимаемся на уровень выше
REPO = pathlib.Path(__file__).resolve().parent.parent
CHAT_ARCHIVES = REPO / "chat-archives"
RAW_BASE = CHAT_ARCHIVES / "raw"
BACKUPS = REPO / "backups"

KEEP_DAYS = 90         # хранить tar.gz
RAW_KEEP_DAYS = 1      # не трогать raw/ папки моложе этого (хук ещё может добавить файлы за сегодня)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def run(args, check=True, timeout=30):
    r = subprocess.run(
        args, cwd=REPO, capture_output=True, timeout=timeout
    )
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", errors="replace"))
    return r


def git(*args, check=True, timeout=30):
    return run(["git"] + list(args), check=check, timeout=timeout)


def ok(msg):
    print(f"  ✅ {msg}")


def warn(msg):
    print(f"  ⚠️  {msg}")


def fail(msg):
    print(f"  ❌ {msg}")


# ---------------------------------------------------------------------------
# step 1 — sanity
# ---------------------------------------------------------------------------

def step_sanity():
    r = git("remote", "-v", check=False)
    out = r.stdout.decode("utf-8", errors="replace")
    if "vladsarov53-prog/AgentHQ" not in out:
        fail(f"Unexpected remote:\n{out}")
        sys.exit(1)
    ok("remote = vladsarov53-prog/AgentHQ")


# ---------------------------------------------------------------------------
# step 2 — pull
# ---------------------------------------------------------------------------

def step_pull():
    git("fetch", "origin", "master")
    git("checkout", "master")
    git("pull", "--ff-only", "origin", "master")
    ok("master up to date")


# ---------------------------------------------------------------------------
# step 3 — metadata
# ---------------------------------------------------------------------------

def collect_meta():
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M")
    iso = now.isoformat()
    sha_short = git("rev-parse", "--short", "HEAD").stdout.decode().strip()
    sha_full = git("rev-parse", "HEAD").stdout.decode().strip()
    files_count = git("ls-files").stdout.decode().count("\n")

    # размер репо без .git
    total = sum(f.stat().st_size for f in REPO.rglob("*")
                if f.is_file() and ".git" not in f.parts)
    repo_size = f"{round(total / 1024 / 1024, 1)} MB"

    return {
        "date": date_str,
        "time": time_str,
        "iso": iso,
        "sha": sha_short,
        "sha_full": sha_full,
        "files": files_count,
        "size": repo_size,
    }


# ---------------------------------------------------------------------------
# step 4-5 — tag
# ---------------------------------------------------------------------------

def step_tag(meta):
    tag = f"backup/{meta['date']}"
    r = git("rev-parse", tag, check=False)
    if r.returncode == 0:
        tag = f"backup/{meta['date']}-{meta['time']}"

    git("tag", "-a", tag, "-m",
        f"Daily snapshot {meta['date']} | SHA {meta['sha']} | {meta['size']} | {meta['files']} files")

    r = git("push", "origin", tag, check=False, timeout=60)
    if r.returncode == 0:
        ok(f"tag {tag} pushed")
    else:
        warn(f"tag {tag} created locally (push failed — non-fatal)")

    meta["tag"] = tag
    return tag


# ---------------------------------------------------------------------------
# step 6 — dirs
# ---------------------------------------------------------------------------

def step_dirs():
    BACKUPS.mkdir(parents=True, exist_ok=True)
    RAW_BASE.mkdir(parents=True, exist_ok=True)
    ok("backups/ and chat-archives/raw/ ready")


# ---------------------------------------------------------------------------
# step 7 — archive raw chat transcripts
# ---------------------------------------------------------------------------

def step_archive_chats():
    today = datetime.now(timezone.utc).date()
    cutoff_raw = today - timedelta(days=RAW_KEEP_DAYS)
    cutoff_archive = today - timedelta(days=KEEP_DAYS)

    archived = []
    cleaned_raw = []
    cleaned_old = []

    # Архивируем raw/YYYY-MM-DD/ старше вчера
    if RAW_BASE.exists():
        for day_dir in sorted(RAW_BASE.iterdir()):
            if not day_dir.is_dir():
                continue
            try:
                day_date = datetime.strptime(day_dir.name, "%Y-%m-%d").date()
            except ValueError:
                continue
            if day_date > cutoff_raw:
                continue  # сегодняшние не трогаем

            tar_path = CHAT_ARCHIVES / f"{day_dir.name}.tar.gz"
            jsonl_count = len(list(day_dir.glob("*.jsonl")))
            with tarfile.open(tar_path, "w:gz", compresslevel=9) as tar:
                tar.add(day_dir, arcname=day_dir.name)
            size_kb = round(tar_path.stat().st_size / 1024, 1)
            archived.append(f"{day_dir.name}: {jsonl_count} сессий, {size_kb} KB")
            shutil.rmtree(day_dir)
            cleaned_raw.append(day_dir.name)

    # Удаляем tar.gz старше 90 дней
    for tf in sorted(CHAT_ARCHIVES.glob("*.tar.gz")):
        try:
            d = datetime.strptime(tf.stem.split(".")[0], "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < cutoff_archive:
            tf.unlink()
            cleaned_old.append(tf.name)

    if archived:
        ok(f"chat archives: {len(archived)} дней заархивировано")
        for a in archived:
            print(f"       {a}")
    else:
        ok("chat archives: нет новых папок для архивации")

    if cleaned_old:
        ok(f"удалено старых архивов (>90 дней): {len(cleaned_old)}")

    return archived, cleaned_old


# ---------------------------------------------------------------------------
# step 8 — index.md
# ---------------------------------------------------------------------------

def step_index(iso):
    lines = [
        "# Chat Archives Index\n",
        f"Обновлено: {iso}  \n",
        f"Хранение: {KEEP_DAYS} дней\n",
        "\n",
        "| Дата | Файл | Размер |\n",
        "|------|------|--------|\n",
    ]
    archives = sorted(CHAT_ARCHIVES.glob("*.tar.gz"))
    if archives:
        for tf in archives:
            sz = round(tf.stat().st_size / 1024, 1)
            try:
                d = tf.stem.split(".")[0]
            except Exception:
                d = tf.name
            lines.append(f"| {d} | {tf.name} | {sz} KB |\n")
    else:
        lines.append("| — | нет архивов | — |\n")

    index_path = CHAT_ARCHIVES / "index.md"
    index_path.write_text("".join(lines), encoding="utf-8")
    ok("chat-archives/index.md обновлён")


# ---------------------------------------------------------------------------
# step 9 — manifest
# ---------------------------------------------------------------------------

def step_manifest(meta, archived, cleaned_old):
    archived_text = "\n".join(f"  - {a}" for a in archived) if archived else "  - нет новых"
    cleaned_text = "\n".join(f"  - {c}" for c in cleaned_old) if cleaned_old else "  - нет"

    content = f"""# Backup snapshot {meta['date']}

- **Tag**: `{meta['tag']}`
- **HEAD SHA (short)**: `{meta['sha']}`
- **HEAD SHA (full)**: `{meta['sha_full']}`
- **UTC timestamp**: {meta['iso']}
- **Размер репо без .git**: {meta['size']}
- **Файлов в Git**: {meta['files']}

## Chat archives

Заархивировано за этот прогон:
{archived_text}

Удалено старых (>{KEEP_DAYS} дней):
{cleaned_text}

## Как восстановить агентную систему

```bash
git clone https://github.com/vladsarov53-prog/AgentHQ.git
cd AgentHQ
git checkout {meta['tag']}
```

## Как восстановить чаты

```bash
git clone https://github.com/vladsarov53-prog/AgentHQ.git
cd AgentHQ
tar -xzf chat-archives/YYYY-MM-DD.tar.gz
jq . YYYY-MM-DD/<session_id>.jsonl
```
"""
    manifest_path = BACKUPS / f"manifest-{meta['date']}.md"
    manifest_path.write_text(content, encoding="utf-8")
    ok(f"backups/manifest-{meta['date']}.md записан")


# ---------------------------------------------------------------------------
# step 10 — log.md
# ---------------------------------------------------------------------------

def step_log(meta):
    log_path = BACKUPS / "log.md"
    header = "# Backup log\n\nЕжедневные snapshots master. Запись добавляется remote-routine.\n\n"
    line = (
        f"- {meta['iso']} | tag `{meta['tag']}` | SHA `{meta['sha']}` "
        f"| {meta['size']} | {meta['files']} файлов\n"
    )
    if not log_path.exists():
        log_path.write_text(header + line, encoding="utf-8")
    else:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    ok("backups/log.md обновлён")


# ---------------------------------------------------------------------------
# step 11 — commit & push
# ---------------------------------------------------------------------------

def step_commit(meta):
    git("add", "backups/", "chat-archives/", check=False)
    r = git("commit", "-m", f"backup: snapshot {meta['date']} [SHA {meta['sha']}]", check=False)
    if r.returncode == 0:
        r2 = git("push", "origin", "master", check=False, timeout=60)
        if r2.returncode == 0:
            ok("commit + push в master")
        else:
            warn(f"push failed: {r2.stderr.decode('utf-8', errors='replace')[:200]}")
    else:
        out = r.stdout.decode("utf-8", errors="replace")
        if "nothing to commit" in out:
            ok("nothing to commit (manifest не изменился)")
        else:
            warn(f"commit error: {out[:200]}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    print("\n=== RedPeak HQ Daily Backup ===")
    print(f"Repo: {REPO}")
    print()

    step_sanity()
    step_pull()
    meta = collect_meta()
    ok(f"metadata: {meta['date']} | SHA {meta['sha']} | {meta['size']} | {meta['files']} files")
    step_dirs()
    step_tag(meta)
    archived, cleaned_old = step_archive_chats()
    step_index(meta["iso"])
    step_manifest(meta, archived, cleaned_old)
    step_log(meta)
    step_commit(meta)

    print()
    print("=== Summary ===")
    print(f"Tag: {meta['tag']}")
    print(f"SHA: {meta['sha']} ({meta['sha_full'][:16]}...)")
    print(f"Repo size: {meta['size']}, {meta['files']} files")
    print(f"Chat archives created: {len(archived)}")
    print(f"Old archives removed: {len(cleaned_old)}")
    print()
    print("Restore agent system:")
    print(f"  git clone https://github.com/vladsarov53-prog/AgentHQ && git checkout {meta['tag']}")
    print("Restore chats:")
    print("  tar -xzf chat-archives/YYYY-MM-DD.tar.gz")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n❌ Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
