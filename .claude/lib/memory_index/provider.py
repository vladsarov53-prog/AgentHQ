"""
Embedding Provider — обёртка над Ollama (приоритет) с fallback на Chroma default.

Стратегия:
1. Если Ollama запущена и модель nomic-embed-text доступна → используем её (768-dim, multilingual).
2. Иначе → Chroma default `all-MiniLM-L6-v2` (384-dim, English) с предупреждением.

Источник: Ollama HTTP API spec (https://github.com/ollama/ollama/blob/main/docs/api.md),
Anthropic «Building Effective Agents» (внешние embedding модели для retrieval).
"""

import json
import sys
import urllib.error
import urllib.request

OLLAMA_DEFAULT_URL = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "nomic-embed-text"
OLLAMA_TIMEOUT_SEC = 30


class EmbeddingError(RuntimeError):
    pass


def is_ollama_available(url=OLLAMA_DEFAULT_URL, timeout=2):
    """Быстрая проверка: Ollama отвечает на /api/tags."""
    try:
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def list_ollama_models(url=OLLAMA_DEFAULT_URL, timeout=3):
    """Возвращает список установленных моделей Ollama."""
    try:
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def ollama_has_model(model_name, url=OLLAMA_DEFAULT_URL):
    """Проверяет, что конкретная модель установлена в Ollama."""
    models = list_ollama_models(url=url)
    # Ollama возвращает имена с тегом: "nomic-embed-text:latest"
    target = model_name.split(":")[0]
    return any(m.split(":")[0] == target for m in models)


def ollama_embed(text, model=OLLAMA_DEFAULT_MODEL, url=OLLAMA_DEFAULT_URL,
                 timeout=OLLAMA_TIMEOUT_SEC, task=None):
    """
    Получить embedding через Ollama HTTP API.

    task: "query" | "document" | None — для моделей с задачными префиксами
    (например, nomic-embed-text v1 требует "search_query:"/"search_document:").
    Возвращает list[float] либо бросает EmbeddingError.
    """
    # Для nomic-embed-text v1 префиксы критичны для качества retrieval
    if task and "nomic-embed-text" in model:
        prefix = "search_query: " if task == "query" else "search_document: "
        text = prefix + text

    body = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/api/embeddings",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            emb = data.get("embedding")
            if not emb or not isinstance(emb, list):
                raise EmbeddingError(
                    f"Ollama вернула некорректный ответ: {str(data)[:200]}"
                )
            return emb
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        raise EmbeddingError(f"Ollama HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise EmbeddingError(f"Ollama URL error: {e.reason}")
    except Exception as e:
        raise EmbeddingError(f"Ollama unexpected: {e}")


class EmbeddingProvider:
    """
    Унифицированный интерфейс. Автоматически выбирает источник эмбеддингов.

    Использование:
        prov = EmbeddingProvider()
        if prov.mode == "ollama":
            emb = prov.embed("текст")  # список float
        elif prov.mode == "chroma_default":
            # Эмбеддинги генерируются Chroma при upsert/query через documents=
            ...
    """

    def __init__(self, prefer_ollama=True, ollama_model=OLLAMA_DEFAULT_MODEL):
        self.ollama_model = ollama_model
        self.mode = "chroma_default"  # fallback по умолчанию
        self.warning = None

        if prefer_ollama:
            if is_ollama_available():
                if ollama_has_model(ollama_model):
                    self.mode = "ollama"
                else:
                    self.warning = (
                        f"Ollama запущена, но модель '{ollama_model}' "
                        f"не установлена. Запусти: ollama pull {ollama_model}"
                    )
            else:
                self.warning = (
                    "Ollama недоступна на localhost:11434. "
                    "Используется встроенная Chroma-модель (English, "
                    "384-dim, посредственное качество на русском)."
                )

    def embed(self, text, task="query"):
        """Получить embedding для одного текста.

        task: "query" — для поисковых запросов; "document" — для индексируемых.
        """
        if self.mode == "ollama":
            return ollama_embed(text, model=self.ollama_model, task=task)
        raise EmbeddingError(
            "embed() недоступен в режиме chroma_default — "
            "Chroma сама генерирует эмбеддинги через documents=. "
            "Используй ChromaIndex.upsert/search вместо прямого embed()."
        )

    def embed_batch(self, texts, task="document"):
        """Получить embeddings для списка текстов (по умолчанию — документы)."""
        if self.mode == "ollama":
            return [
                ollama_embed(t, model=self.ollama_model, task=task)
                for t in texts
            ]
        raise EmbeddingError("embed_batch() недоступен в режиме chroma_default")

    def status_line(self):
        """Одна строка для логов / CLI о статусе провайдера."""
        if self.mode == "ollama":
            return f"Embedding: Ollama ({self.ollama_model}, multilingual, ~768-dim)"
        return f"Embedding: Chroma default (all-MiniLM-L6-v2, English, 384-dim)"


if __name__ == "__main__":
    # Smoke-test: проверить что провайдер инициализируется
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = EmbeddingProvider()
    print(p.status_line())
    if p.warning:
        print(f"WARN: {p.warning}")
    if p.mode == "ollama":
        try:
            emb = p.embed("Тестовый текст для проверки эмбеддинга")
            print(f"Embedding получен, размерность: {len(emb)}")
        except EmbeddingError as e:
            print(f"Ошибка эмбеддинга: {e}")
