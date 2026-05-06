"""
Memory Search Eval — замер качества semantic search на тестовом наборе.

20 типичных запросов с ground-truth (какой entity_id ожидается в топе).
Метрики: Recall@1, Recall@3, Recall@5, средняя similarity.

Использование:
    .claude/venv_chroma/Scripts/python.exe .claude/tests/L7_monitoring/memory_search_eval.py
    .claude/venv_chroma/Scripts/python.exe .claude/tests/L7_monitoring/memory_search_eval.py --json

Источник: information retrieval evaluation (Recall@K — стандартная метрика
для retrieval-augmented systems, см. BEIR benchmark).
"""

import argparse
import json
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


# 20 тестовых запросов с ожидаемыми entity IDs.
# В expected — список ID, любой из которых считается "правильным" ответом.
TEST_CASES = [
    # — Контакты —
    {
        "id": "T-1",
        "query": "встреча с Константином",
        "expected": ["contact_konstantin"],
    },
    {
        "id": "T-2",
        "query": "кто отвечает за бухгалтерию",
        "expected": ["contact_svetlana"],
    },
    {
        "id": "T-3",
        "query": "член команды Сколково финплан",
        "expected": ["contact_konstantin"],
    },
    # — Проекты —
    {
        "id": "T-4",
        "query": "грант ФСИ статус",
        "expected": ["project_grant_fsi"],
    },
    {
        "id": "T-5",
        "query": "статус Сколково",
        "expected": ["project_skolkovo"],
    },
    {
        "id": "T-6",
        "query": "уведомление о льготах ФНС",
        "expected": ["project_skolkovo_tax_notice"],
    },
    {
        "id": "T-7",
        "query": "договор с CAD-разработчиком",
        "expected": ["project_cad_contract", "decision_cad_v3.4_2026-04-25"],
    },
    {
        "id": "T-8",
        "query": "переговоры с ML-инженером",
        "expected": ["project_ml_negotiations"],
    },
    {
        "id": "T-9",
        "query": "налоговая декларация ООО",
        "expected": ["project_tax_declaration"],
    },
    {
        "id": "T-10",
        "query": "хостинг бота на Railway",
        "expected": ["project_bot_hosting"],
    },
    {
        "id": "T-11",
        "query": "приоритеты на эту неделю",
        "expected": ["project_current_focus"],
    },
    # — Решения —
    {
        "id": "T-12",
        "query": "почему перешли на v3.4 в CAD",
        "expected": ["decision_cad_v3.4_2026-04-25"],
    },
    {
        "id": "T-13",
        "query": "выносные элементы в чертежах",
        "expected": ["decision_cad_detail_views_2026-04-23"],
    },
    {
        "id": "T-14",
        "query": "консолидация комплекта документов",
        "expected": ["decision_cad_docs_consolidation_2026-04-23"],
    },
    # — Правила работы (feedback) —
    {
        "id": "T-15",
        "query": "не выдумывать факты в документах",
        "expected": ["feedback_no_invented_facts"],
    },
    {
        "id": "T-16",
        "query": "длинные тире в текстах",
        "expected": ["feedback_no_em_dash"],
    },
    {
        "id": "T-17",
        "query": "проверять источник точно",
        "expected": ["feedback_check_source_precisely",
                     "feedback_check_data_first"],
    },
    {
        "id": "T-18",
        "query": "Python UTF-8 на Windows",
        "expected": ["feedback_python_utf8_windows"],
    },
    {
        "id": "T-19",
        "query": "автоматически записывать ошибки",
        "expected": ["feedback_auto_log_errors"],
    },
    # — Профиль пользователя —
    {
        "id": "T-20",
        "query": "кто такой основатель RedPeak",
        "expected": ["user_profile"],
    },
]


def evaluate(top_k=5, mode="hybrid"):
    """
    mode: "vector" | "hybrid"
    """
    provider = EmbeddingProvider()
    index = ChromaIndex(provider=provider)
    status = index.status()

    if status["count"] == 0:
        return {
            "error": "Chroma коллекция пуста. Запусти memory_reindex.py.",
            "embedding_mode": status["embedding_mode"],
        }

    hybrid = HybridSearch(chroma_index=index) if mode == "hybrid" else None

    results_per_case = []
    recall_at_1 = 0
    recall_at_3 = 0
    recall_at_5 = 0
    sum_top1_similarity = 0.0
    correct_count = 0

    for case in TEST_CASES:
        if mode == "hybrid":
            raw = hybrid.search(case["query"], n_results=top_k)
            results = []
            for r in raw:
                results.append({
                    "id": r["id"],
                    "similarity": r.get("vector_similarity") or 0.0,
                })
        else:
            results = index.search(case["query"], n_results=top_k)
        result_ids = [r["id"] for r in results]
        top1 = result_ids[0] if result_ids else None
        top1_sim = results[0]["similarity"] if results else 0.0
        sum_top1_similarity += top1_sim

        expected_set = set(case["expected"])
        in_top_1 = bool(expected_set & set(result_ids[:1]))
        in_top_3 = bool(expected_set & set(result_ids[:3]))
        in_top_5 = bool(expected_set & set(result_ids[:5]))

        if in_top_1:
            recall_at_1 += 1
        if in_top_3:
            recall_at_3 += 1
        if in_top_5:
            recall_at_5 += 1
        if in_top_3:
            correct_count += 1

        results_per_case.append({
            "id": case["id"],
            "query": case["query"],
            "expected": case["expected"],
            "top_results": result_ids,
            "top1_similarity": round(top1_sim, 3),
            "in_top_1": in_top_1,
            "in_top_3": in_top_3,
            "in_top_5": in_top_5,
        })

    n = len(TEST_CASES)
    return {
        "embedding_mode": status["embedding_mode"],
        "embedding_warning": status.get("embedding_warning"),
        "search_mode": mode,
        "total_cases": n,
        "metrics": {
            "recall_at_1": round(recall_at_1 / n, 3),
            "recall_at_3": round(recall_at_3 / n, 3),
            "recall_at_5": round(recall_at_5 / n, 3),
            "mean_top1_similarity": round(sum_top1_similarity / n, 3),
        },
        "cases": results_per_case,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--mode", type=str, default="hybrid",
                        choices=["vector", "hybrid"],
                        help="Режим поиска: vector (только embedding) или hybrid (BM25+vector)")
    parser.add_argument("--compare", action="store_true",
                        help="Прогнать оба режима и сравнить")
    args = parser.parse_args()

    if args.compare:
        r_vec = evaluate(top_k=args.top_k, mode="vector")
        r_hyb = evaluate(top_k=args.top_k, mode="hybrid")
        if "error" in r_vec or "error" in r_hyb:
            print("Error in eval, see above")
            sys.exit(1)
        print(f"\n{'='*72}")
        print(f"  Comparison: vector vs hybrid")
        print(f"  Embedding mode: {r_vec['embedding_mode']}")
        print(f"{'='*72}\n")
        print(f"  {'Metric':<22} {'Vector':>10} {'Hybrid':>10} {'Δ':>8}")
        for k in ("recall_at_1", "recall_at_3", "recall_at_5",
                  "mean_top1_similarity"):
            v = r_vec["metrics"][k]
            h = r_hyb["metrics"][k]
            delta = h - v
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
            print(f"  {k:<22} {v:>10.3f} {h:>10.3f} {delta:>+7.3f} {arrow}")
        print()
        return

    result = evaluate(top_k=args.top_k, mode=args.mode)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if "error" in result:
        print(f"\n[ERROR] {result['error']}")
        sys.exit(1)

    m = result["metrics"]
    print(f"\n{'='*72}")
    print(f"  Memory Search Evaluation")
    print(f"  Embedding mode: {result['embedding_mode']}")
    if result.get("embedding_warning"):
        print(f"  WARN: {result['embedding_warning']}")
    print(f"{'='*72}\n")

    print(f"  Cases:           {result['total_cases']}")
    print(f"  Recall@1:        {m['recall_at_1']*100:.1f}%")
    print(f"  Recall@3:        {m['recall_at_3']*100:.1f}%")
    print(f"  Recall@5:        {m['recall_at_5']*100:.1f}%")
    print(f"  Mean top1 sim:   {m['mean_top1_similarity']:.3f}")

    print(f"\n  Acceptance:")
    print(f"    Recall@3 >= 75%   {'PASS' if m['recall_at_3'] >= 0.75 else 'FAIL'}")
    print(f"    Recall@3 >= 90%   {'EXCELLENT' if m['recall_at_3'] >= 0.90 else '-'}")

    failed = [c for c in result["cases"] if not c["in_top_3"]]
    if failed:
        print(f"\n  Провалили top-3 ({len(failed)} кейсов):")
        for c in failed:
            print(f"    {c['id']}: '{c['query']}'")
            print(f"      ожидали: {c['expected']}")
            print(f"      получили: {c['top_results'][:3]}")

    print(f"\n{'='*72}\n")


if __name__ == "__main__":
    main()
