"""
Memory Reindex CLI
Полная реиндексация auto-memory в Chroma.

Запуск (через venv с chromadb):
    .claude/venv_chroma/Scripts/python.exe .claude/tests/L7_monitoring/memory_reindex.py
    .claude/venv_chroma/Scripts/python.exe .claude/tests/L7_monitoring/memory_reindex.py --dry-run

Когда запускать:
- После установки/обновления Ollama (чтобы перегенерить embeddings)
- После массовых правок в auto-memory
- При первом запуске системы

Источник: best practice для индексаций — full rebuild при смене embedding-модели.
"""

import argparse
import os
import sys
from pathlib import Path

# Добавляем .claude/lib в путь
SCRIPT_DIR = Path(__file__).resolve().parent
LIB_DIR = SCRIPT_DIR.parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from memory_index.parser import find_auto_memory_dir, parse_all_memory
from memory_index.provider import EmbeddingProvider
from memory_index.index import ChromaIndex


def main():
    parser = argparse.ArgumentParser(description="Reindex AgentHQ auto-memory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Только парсинг, без записи в Chroma")
    parser.add_argument("--memory-dir", type=str, default=None,
                        help="Override auto-memory dir")
    parser.add_argument("--clear-first", action="store_true",
                        help="Очистить коллекцию перед реиндексом")
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print("  AgentHQ Memory Reindex")
    print(f"{'='*70}")

    mem_dir = args.memory_dir or find_auto_memory_dir()
    if not mem_dir:
        print("[ERROR] auto-memory директория не найдена")
        sys.exit(1)
    print(f"  Memory dir: {mem_dir}")

    # 1. Парсинг
    entities = parse_all_memory(mem_dir)
    print(f"  Найдено entities: {len(entities)}")
    if not entities:
        print("  Нечего индексировать")
        sys.exit(0)

    if args.dry_run:
        print("\n  --dry-run: пропускаю запись в Chroma")
        for e in entities:
            print(f"    {e['id']:50} type={e['type']:10} {len(e['full_text'])} chars")
        sys.exit(0)

    # 2. Провайдер
    provider = EmbeddingProvider()
    print(f"  {provider.status_line()}")
    if provider.warning:
        print(f"  WARN: {provider.warning}")

    # 3. Индекс
    index = ChromaIndex(provider=provider)
    status = index.status()
    print(f"  Chroma DB: {status['db_path']}")
    print(f"  До реиндекса в коллекции: {status['count']} записей")

    # 4. Очистка (опционально)
    if args.clear_first:
        existing_ids = index.list_all_ids()
        if existing_ids:
            index.delete(existing_ids)
            print(f"  Очищено: {len(existing_ids)} старых записей")

    # 5. Подготовка batch
    batch = []
    for e in entities:
        batch.append({
            "id": e["id"],
            "text": e["full_text"],
            "metadata": {
                "name": e["name"],
                "type": e["type"],
                "description": e["description"][:500],
                "file_path": e["file_path"],
                "mtime": int(e["mtime"]),
            },
        })

    # 6. Upsert
    print(f"\n  Индексация {len(batch)} entities...")
    try:
        n = index.upsert(batch)
        print(f"  OK: записано {n}")
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(2)

    final_status = index.status()
    print(f"\n  В коллекции после: {final_status['count']} записей")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
