# Этап 3.2 — Векторная память (семантический поиск)

**Статус:** план, требует отдельной сессии. **Высокий риск регрессии — выделить полный фокус.**

## Задача

Сейчас память — JSONL + knowledge graph. Поиск только по типам entities (`obligation`, `decision`, ...) и точному матчу. Запрос «что важно для встречи с Константином» система не найдёт без явного упоминания имени в `entityName`.

Нужен embedding-based retrieval поверх существующей memory.

## Опции (3 варианта)

### Вариант А: Mem0 MCP (managed, OpenAI/Anthropic embeddings)
- Replace `@modelcontextprotocol/server-memory` на `@mem0ai/mcp-server`.
- **Плюсы:** drop-in replacement, hot vector search out of the box, multi-user поддержка.
- **Минусы:** depends on external API for embeddings ($), смена data format → нужен data migration.
- **Стоимость:** $20/мес базовый план + embedding API costs.
- **Источник:** mem0.ai, GitHub mem0ai/mem0.

### Вариант Б: Локальный Chroma + embeddings через Ollama
- Установить `chromadb` Python пакет, embeddings — `nomic-embed-text` через локальный Ollama.
- Hook на запись в knowledge_graph.json параллельно делает embedding и пишет в Chroma.
- **Плюсы:** полностью локально, $0, не зависит от внешних API.
- **Минусы:** требует Ollama runtime (1-2 ГБ дисковое + ~500 МБ RAM), сложнее в поддержке.
- **Источник:** chromadb, ollama.ai.

### Вариант В: Hybrid — оставить knowledge_graph.json, добавить векторный поиск как дополнение
- Не заменяем память, дополняем. Существующие целевые запросы из CLAUDE.md работают как есть.
- Embedding-индекс — отдельный, обновляется хуком при изменении knowledge_graph.json.
- **Плюсы:** zero-risk migration, обратимо, не ломает существующую интеграцию.
- **Минусы:** двойное хранение, нужна синхронизация.
- **Источник:** [МОЯ ИНТЕРПРЕТАЦИЯ] best practice для миграции production-памяти — никогда не удалять существующее, дополнять.

## Рекомендация

**Вариант В — гибрид.**

Аргументация:
- Память сейчас содержит критичные данные (контракт CAD, расходы по гранту, контакты). Терять нельзя.
- Хочется проверить улучшение от семантического поиска до коммита на Mem0 ($240/год)
- Если эффект будет — мигрировать на Mem0 проще из работающего гибрида
- Если нет — можно откатить только embedding-индекс, основная память не трогается

## Что нужно для реализации (отдельная сессия, ~4-6 часов работы)

### Шаг 1: Embeddings infrastructure
- Установить `chromadb` локально (через pip)
- Установить Ollama + `nomic-embed-text` (один раз)
- `.claude/hooks/memory-index.py` — PostToolUse на изменение `memory/knowledge_graph.json`:
  - Парсит изменения, для каждого entity создаёт/обновляет embedding в Chroma

### Шаг 2: Search API
- `.claude/tests/L7_monitoring/memory_semantic_search.py` — CLI для теста
- Запрос: `python ... search "встреча с Константином"` → топ-5 entities с similarity score

### Шаг 3: Интеграция в субагентов
- Обновить промпты operations/strategy/legal/accounting:
  - Добавить инструкцию использовать `memory_semantic_search` для не-точных запросов
  - Точные запросы (по типу entity) — как было

### Шаг 4: L1+L2 тесты
- 6-8 unit-тестов нового хука
- 2-3 golden-теста: проверка что поиск находит правильные entities

### Шаг 5: A/B сравнение
- Тестовый набор из 20 типичных запросов
- Сравнить: результат без semantic vs с semantic
- Метрика: точность top-3 (есть ли нужный entity в первых трёх результатах)

## Риски

- **Высокий:** изменения в субагентах могут дать регрессию по L2 golden tests. Прогон ОБЯЗАТЕЛЕН после каждого изменения промпта.
- **Средний:** Ollama может не запуститься на Windows / 32-bit ОС. Бэкап-план: пройти через Anthropic embeddings API ($).
- **Низкий:** двойное хранение — ~2 МБ для текущей памяти. Не проблема.

## Стоп-точки

- Перед удалением старого memory MCP — explicit confirmation
- Перед изменением CLAUDE.md (раздел про целевые запросы к памяти) — confirmation
- Перед merge worktree → master — финальный регрессионный прогон

## Acceptance Criteria

- [ ] Семантический поиск возвращает релевантные entities на 15+ из 20 тестовых запросов
- [ ] Существующие целевые запросы в CLAUDE.md работают без изменений (обратная совместимость)
- [ ] Memory MCP сохраняет работоспособность (deep_check проходит)
- [ ] L1: рост покрытия (новые тесты на memory-index hook)
- [ ] L2: golden tests проходят без регрессии

## Источники [МОЯ ИНТЕРПРЕТАЦИЯ из публичной документации]

- Mem0 — production-grade memory layer for LLMs
- Chroma — open-source embedding database
- Ollama — local LLM runtime
- Anthropic «Building Effective Agents» — memory как контекст
- Подход hybrid migration — стандарт refactoring для производственных систем
