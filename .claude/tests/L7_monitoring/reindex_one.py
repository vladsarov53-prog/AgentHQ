"""
Reindex One — индексирует/обновляет один файл auto-memory в Chroma.

Запускается из memory-index.py hook через venv-python.
Аргумент: путь к .md файлу.

Источник: incremental indexing pattern, чтобы не делать полный reindex
на каждое изменение.
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LIB_DIR = SCRIPT_DIR.parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from memory_index.parser import parse_memory_file
from memory_index.provider import EmbeddingProvider
from memory_index.index import ChromaIndex


def main():
    if len(sys.argv) < 2:
        print("Usage: reindex_one.py <path-to-md-file>")
        sys.exit(1)

    file_path = sys.argv[1]
    p = Path(file_path)

    provider = EmbeddingProvider()
    index = ChromaIndex(provider=provider)

    if not p.exists():
        # Файл удалён — удаляем из индекса по ID = stem
        index.delete([p.stem])
        print(f"Removed from index: {p.stem}")
        sys.exit(0)

    entity = parse_memory_file(p)
    if entity is None:
        sys.exit(0)

    batch = [{
        "id": entity["id"],
        "text": entity["full_text"],
        "metadata": {
            "name": entity["name"],
            "type": entity["type"],
            "description": entity["description"][:500],
            "file_path": entity["file_path"],
            "mtime": int(entity["mtime"]),
        },
    }]
    index.upsert(batch)
    print(f"Indexed: {entity['id']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Hook вызывает с capture_output, ошибки не критичны
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
