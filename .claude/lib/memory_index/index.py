"""
ChromaIndex — обёртка над Chroma collection с поддержкой двух режимов:
  - "ollama":  embeddings приходят от Ollama (внешне, передаются явно)
  - "chroma_default": эмбеддинги генерирует Chroma из documents=

Coллекция: agenthq_memory
Path: memory/chroma_db/  (внутри проекта, можно gitignore)

Источник: chromadb docs (https://docs.trychroma.com/), best practices for hybrid retrieval.
"""

from pathlib import Path

import chromadb

from .provider import EmbeddingProvider


COLLECTION_NAME = "agenthq_memory"

# nomic-embed-text в Ollama по умолчанию использует num_ctx=2048 токенов.
# Для русского ~2.5 char/token, безопасно ставим 2500 chars (~1000 токенов).
# Для retrieval head/intro важнее тела — длинные карточки обрезаем.
MAX_EMBEDDING_TEXT_CHARS = 2500


def find_project_root():
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "CLAUDE.md").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent.parent


class ChromaIndex:
    """
    Векторный индекс для AgentHQ memory.

    upsert/search автоматически работают в обоих режимах эмбеддингов.
    """

    def __init__(self, db_path=None, provider=None):
        self.project_root = find_project_root()
        self.db_path = (
            Path(db_path) if db_path
            else self.project_root / "memory" / "chroma_db"
        )
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.provider = provider or EmbeddingProvider()

        self.client = chromadb.PersistentClient(path=str(self.db_path))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},  # косинусная мера
        )

    def status(self):
        return {
            "db_path": str(self.db_path),
            "collection": COLLECTION_NAME,
            "count": self.collection.count(),
            "embedding_mode": self.provider.mode,
            "embedding_warning": self.provider.warning,
        }

    def upsert(self, entities):
        """
        Добавить или обновить entities.

        entities — список dict с полями: id, text, metadata.
        """
        if not entities:
            return 0
        ids = [e["id"] for e in entities]
        # Обрезаем длинные тексты под лимит контекста embedding-модели
        texts = [
            (e["text"][:MAX_EMBEDDING_TEXT_CHARS] if e["text"] else "")
            for e in entities
        ]
        metadatas = [e.get("metadata") or {} for e in entities]

        # Chroma не принимает None и nested dicts в metadata
        clean_meta = []
        for m in metadatas:
            cleaned = {}
            for k, v in m.items():
                if v is None:
                    continue
                if isinstance(v, (str, int, float, bool)):
                    cleaned[k] = v
                else:
                    cleaned[k] = str(v)
            clean_meta.append(cleaned)

        if self.provider.mode == "ollama":
            # При индексации используем task="document"
            embeddings = self.provider.embed_batch(texts, task="document")
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=clean_meta,
            )
        else:
            # Chroma сама генерирует embeddings из documents
            self.collection.upsert(
                ids=ids,
                documents=texts,
                metadatas=clean_meta,
            )
        return len(entities)

    def delete(self, ids):
        """Удалить entities по ID."""
        if not ids:
            return 0
        self.collection.delete(ids=ids)
        return len(ids)

    def search(self, query_text, n_results=5, where=None):
        """
        Семантический поиск по запросу.

        Возвращает list[dict] с полями: id, text, metadata, distance, similarity.
        similarity = 1 - distance (для cosine, 1.0 = идентично, 0.0 = противоположно).
        """
        if self.provider.mode == "ollama":
            # При поиске используем task="query"
            query_emb = self.provider.embed(
                query_text[:MAX_EMBEDDING_TEXT_CHARS],
                task="query",
            )
            res = self.collection.query(
                query_embeddings=[query_emb],
                n_results=n_results,
                where=where,
            )
        else:
            res = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where,
            )

        results = []
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        for i in range(len(ids)):
            dist = dists[i] if i < len(dists) else 1.0
            results.append({
                "id": ids[i],
                "text": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "distance": dist,
                "similarity": max(0.0, 1.0 - dist),
            })
        return results

    def list_all_ids(self):
        """Возвращает все IDs в коллекции (для проверки целостности)."""
        try:
            res = self.collection.get(include=[])
            return res.get("ids", [])
        except Exception:
            return []
