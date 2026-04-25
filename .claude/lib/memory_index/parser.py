"""
Parser для AgentHQ auto-memory файлов.

Auto-memory лежит в C:/Users/<user>/.claude/projects/<slug>/memory/*.md
Каждый файл — одна entity с YAML frontmatter (name, description, type) + body.

Источник: системные инструкции AgentHQ "auto memory" формат
(см. CLAUDE.md, раздел "Умная память").
"""

import os
import re
import sys
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def find_auto_memory_dir():
    """
    Возвращает путь к auto-memory директории Claude Code.

    На Windows: %USERPROFILE%/.claude/projects/<project-slug>/memory/
    Slug формируется заменой разделителей пути на дефисы.
    """
    home = Path(os.path.expanduser("~"))
    projects_dir = home / ".claude" / "projects"
    if not projects_dir.exists():
        return None

    # Ищем папку с памятью этого проекта
    # Slug RedPeak: D--REDPEAK-Agent-systems-AgentHQ
    candidates = []
    for d in projects_dir.iterdir():
        if d.is_dir():
            mem = d / "memory"
            if mem.exists() and any(mem.glob("*.md")):
                candidates.append(mem)

    # Если несколько проектов — берём с самым свежим mtime
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def parse_memory_file(file_path):
    """
    Парсит один .md файл памяти.

    Возвращает dict: {id, name, description, type, body, full_text, file_path, mtime}
    Либо None при ошибке.
    """
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return None
    if p.name.upper() == "MEMORY.MD":
        return None  # MEMORY.md — индекс, не сама память

    try:
        content = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    # Парсим frontmatter
    match = FRONTMATTER_RE.match(content)
    name = p.stem
    description = ""
    type_ = "unknown"
    body = content

    if match:
        fm_text = match.group(1)
        body = match.group(2).strip()
        for line in fm_text.split("\n"):
            line = line.strip()
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
            elif line.startswith("type:"):
                type_ = line.split(":", 1)[1].strip()

    # ID = имя файла без расширения (стабильный)
    entity_id = p.stem

    # Текст для эмбеддинга = name + description + body
    full_text_parts = []
    if name:
        full_text_parts.append(f"# {name}")
    if description:
        full_text_parts.append(description)
    if body:
        full_text_parts.append(body)
    full_text = "\n\n".join(full_text_parts)

    return {
        "id": entity_id,
        "name": name,
        "description": description,
        "type": type_,
        "body": body,
        "full_text": full_text,
        "file_path": str(p),
        "mtime": p.stat().st_mtime,
    }


def parse_all_memory(memory_dir=None):
    """
    Парсит все .md файлы в auto-memory директории.

    Возвращает list[dict] (см. parse_memory_file).
    """
    if memory_dir is None:
        memory_dir = find_auto_memory_dir()
    if memory_dir is None:
        return []

    memory_dir = Path(memory_dir)
    entities = []
    for p in memory_dir.glob("*.md"):
        ent = parse_memory_file(p)
        if ent is not None:
            entities.append(ent)
    return entities


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    mem_dir = find_auto_memory_dir()
    print(f"Memory directory: {mem_dir}")
    if mem_dir:
        entities = parse_all_memory(mem_dir)
        print(f"Parsed {len(entities)} entities:")
        for e in entities[:10]:
            print(f"  - {e['id']} (type={e['type']}, {len(e['full_text'])} chars)")
        if len(entities) > 10:
            print(f"  ... и ещё {len(entities) - 10}")
