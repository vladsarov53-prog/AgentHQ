"""
Hybrid Search — BM25 (лексический) + Vector (семантический) с RRF fusion.

На малых корпусах (~десятки entities) чистый vector retrieval часто проигрывает
лексическому. Гибрид через Reciprocal Rank Fusion даёт лучшее из обоих.

Источник: Anthropic «Building Effective Agents» (multi-strategy retrieval),
BEIR benchmark (BM25 + dense даёт SOTA на маленьких корпусах),
Cormack et al. 2009 (RRF — reciprocal rank fusion).
"""

import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from .index import ChromaIndex, MAX_EMBEDDING_TEXT_CHARS
from .parser import parse_all_memory


# Простой токенизатор для русского/английского:
# - lowercase
# - выделяем последовательности букв/цифр (включая русские)
TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Минимальные стоп-слова — не вырезаем агрессивно, чтобы не ломать короткие запросы
STOP_WORDS = {
    "и", "в", "на", "с", "по", "к", "о", "об", "из", "за", "от", "до",
    "the", "a", "an", "of", "to", "in", "is", "for", "on",
}


def tokenize(text):
    """Токенизация: lowercase + слова. Стоп-слова удалены."""
    if not text:
        return []
    tokens = TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


class HybridSearch:
    """
    Гибридный поиск: BM25 (по токенам) + Chroma (по эмбеддингам) → RRF.

    Использование:
        h = HybridSearch()  # автоматом строит BM25 индекс по auto-memory
        results = h.search("встреча с Константином", n_results=5)
    """

    def __init__(self, chroma_index=None, memory_entities=None):
        self.chroma = chroma_index or ChromaIndex()
        # Если entities не переданы — парсим заново
        if memory_entities is None:
            memory_entities = parse_all_memory()
        self.entities = memory_entities

        # Строим BM25 индекс
        self.corpus_tokens = []
        self.entity_ids = []
        for e in self.entities:
            text = (e.get("full_text") or "")[:MAX_EMBEDDING_TEXT_CHARS]
            tokens = tokenize(text)
            self.corpus_tokens.append(tokens)
            self.entity_ids.append(e["id"])

        if self.corpus_tokens:
            self.bm25 = BM25Okapi(self.corpus_tokens)
        else:
            self.bm25 = None

    def _bm25_top(self, query, n):
        if not self.bm25:
            return []
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scores = self.bm25.get_scores(q_tokens)
        # Сортируем по scores
        ranked = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )
        results = []
        for idx in ranked[:n]:
            if scores[idx] <= 0:
                break
            results.append({
                "id": self.entity_ids[idx],
                "score": float(scores[idx]),
            })
        return results

    def _vector_top(self, query, n):
        return self.chroma.search(query, n_results=n)

    @staticmethod
    def _rrf(rankings_list, k=60):
        """
        Reciprocal Rank Fusion: combine rankings из разных retrievers.

        rankings_list — список списков (каждый список = отсортированные id).
        k=60 — стандартный hyperparameter (Cormack et al.)

        Возвращает: dict id → score (выше = лучше).
        """
        scores = {}
        for ranking in rankings_list:
            for rank, item_id in enumerate(ranking):
                scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
        return scores

    def search(self, query, n_results=5, n_pool=20):
        """
        Гибридный поиск. n_pool — сколько кандидатов брать из каждого retriever
        перед слиянием. n_results — сколько финальных результатов выдать.
        """
        # 1. BM25
        bm25_hits = self._bm25_top(query, n_pool)
        bm25_ids = [h["id"] for h in bm25_hits]

        # 2. Vector
        vec_hits = self._vector_top(query, n_pool)
        vec_ids = [h["id"] for h in vec_hits]

        # 3. RRF fusion
        fused_scores = self._rrf([bm25_ids, vec_ids])

        # 4. Сортируем по fused score, берём top n
        sorted_ids = sorted(
            fused_scores.keys(),
            key=lambda i: fused_scores[i],
            reverse=True,
        )[:n_results]

        # 5. Обогащаем метаданными из vector results где есть
        vec_by_id = {h["id"]: h for h in vec_hits}
        bm25_by_id = {h["id"]: h for h in bm25_hits}
        ent_by_id = {e["id"]: e for e in self.entities}

        results = []
        for eid in sorted_ids:
            vec = vec_by_id.get(eid)
            bm25 = bm25_by_id.get(eid)
            ent = ent_by_id.get(eid, {})
            results.append({
                "id": eid,
                "fused_score": round(fused_scores[eid], 4),
                "in_bm25": eid in bm25_ids,
                "in_vector": eid in vec_ids,
                "vector_similarity": round(vec["similarity"], 3) if vec else None,
                "bm25_score": round(bm25["score"], 3) if bm25 else None,
                "name": ent.get("name", eid),
                "type": ent.get("type", "unknown"),
                "description": ent.get("description", ""),
                "file_path": ent.get("file_path", ""),
            })
        return results
