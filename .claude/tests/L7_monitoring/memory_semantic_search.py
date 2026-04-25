"""
Memory Semantic Search CLI
Семантический поиск по auto-memory через Chroma.

Запуск:
    .claude/venv_chroma/Scripts/python.exe .claude/tests/L7_monitoring/memory_semantic_search.py "встреча с Константином"
    .claude/venv_chroma/Scripts/python.exe .claude/tests/L7_monitoring/memory_semantic_search.py "что важно про сколково" --top 3

Использование из субагентов: вместо ручного перебора entities в auto-memory
запускаешь этот CLI с естественным запросом, получаешь топ-N релевантных
с similarity-score. Дальше читаешь полные .md файлы только релевантных.

Источник: retrieval-augmented patterns (Anthropic «Building Effective Agents»).
"""

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LIB_DIR = SCRIPT_DIR.parent.parent / "lib"
sys.path.insert(0, str(LIB_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from memory_index.provider import EmbeddingProvider
from memory_index.index import ChromaIndex
from memory_index.hybrid import HybridSearch


def main():
    parser = argparse.ArgumentParser(description="Semantic search over auto-memory")
    parser.add_argument("query", type=str, help="Текст запроса")
    parser.add_argument("--top", type=int, default=5, help="Сколько результатов")
    parser.add_argument("--type", type=str, default=None,
                        help="Фильтр по типу entity (decision/contact/feedback/...) "
                             "[работает только в --mode vector]")
    parser.add_argument("--json", action="store_true",
                        help="Вывод в JSON (для интеграции с субагентами)")
    parser.add_argument("--min-similarity", type=float, default=0.0,
                        help="Минимальная similarity (0..1) [только в --mode vector]")
    parser.add_argument("--mode", type=str, default="hybrid",
                        choices=["vector", "hybrid"],
                        help="Режим: hybrid (BM25+vector, по умолчанию) или vector")
    args = parser.parse_args()

    provider = EmbeddingProvider()
    index = ChromaIndex(provider=provider)
    status = index.status()

    if status["count"] == 0:
        if args.json:
            print(json.dumps({
                "error": "Chroma collection пуста. Запусти memory_reindex.py.",
                "results": [],
            }, ensure_ascii=False))
        else:
            print("[ERROR] Chroma коллекция пуста.")
            print("        Запусти: .claude/venv_chroma/Scripts/python.exe "
                  ".claude/tests/L7_monitoring/memory_reindex.py")
        sys.exit(1)

    where = {"type": args.type} if args.type else None

    try:
        if args.mode == "hybrid":
            hybrid = HybridSearch(chroma_index=index)
            raw = hybrid.search(args.query, n_results=args.top)
            # Унифицируем формат с vector-режимом
            results = []
            for r in raw:
                results.append({
                    "id": r["id"],
                    "similarity": r.get("vector_similarity") or 0.0,
                    "fused_score": r.get("fused_score"),
                    "in_bm25": r.get("in_bm25"),
                    "in_vector": r.get("in_vector"),
                    "metadata": {
                        "name": r.get("name", r["id"]),
                        "type": r.get("type", "unknown"),
                        "description": r.get("description", ""),
                        "file_path": r.get("file_path", ""),
                    },
                    "distance": None,
                })
        else:
            results = index.search(args.query, n_results=args.top, where=where)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e), "results": []}, ensure_ascii=False))
        else:
            print(f"[ERROR] поиск упал: {e}")
        sys.exit(2)

    # Фильтр по min_similarity (только если есть similarity)
    if args.mode == "vector":
        results = [r for r in results if r["similarity"] >= args.min_similarity]

    if args.json:
        out = []
        for r in results:
            out.append({
                "id": r["id"],
                "similarity": round(r["similarity"], 4),
                "distance": round(r["distance"], 4),
                "name": r["metadata"].get("name", r["id"]),
                "type": r["metadata"].get("type", "unknown"),
                "description": r["metadata"].get("description", ""),
                "file_path": r["metadata"].get("file_path", ""),
            })
        print(json.dumps({
            "query": args.query,
            "embedding_mode": status["embedding_mode"],
            "results": out,
        }, ensure_ascii=False, indent=2))
        return

    print(f"\n{'='*70}")
    print(f"  Запрос: {args.query}")
    print(f"  Search mode: {args.mode}")
    print(f"  Embedding: {status['embedding_mode']}")
    if status.get("embedding_warning"):
        print(f"  WARN: {status['embedding_warning']}")
    print(f"  Результатов: {len(results)}")
    print(f"{'='*70}\n")

    if not results:
        print("  Ничего не найдено.")
        if args.min_similarity > 0:
            print(f"  (фильтр: similarity >= {args.min_similarity})")
        return

    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        name = meta.get("name", r["id"])
        type_ = meta.get("type", "?")
        desc = (meta.get("description") or "")[:120]
        print(f"  {i}. {r['id']}")
        if args.mode == "hybrid":
            sources = []
            if r.get("in_bm25"):
                sources.append("BM25")
            if r.get("in_vector"):
                sources.append("vector")
            print(
                f"     fused={r.get('fused_score'):.4f}  "
                f"vec_sim={r['similarity']:.3f}  "
                f"sources=[{','.join(sources)}]  "
                f"type={type_}  name={name}"
            )
        else:
            print(f"     similarity={r['similarity']:.3f}  type={type_}  name={name}")
        if desc:
            print(f"     {desc}")
        print()


if __name__ == "__main__":
    main()
