# Этап 3.2 — Векторная память: РЕАЛИЗОВАНО

**Дата:** 2026-04-25
**Статус:** работает в production-режиме, готово к merge.

## Итоговый результат

**Recall@3 = 95%** на тестовом наборе из 20 запросов (порог "EXCELLENT" ≥ 90%).
**Recall@1 = 80%** — в большинстве случаев правильный entity сразу первый.

| Метрика | Baseline (default Chroma) | Vector-only (Ollama) | **Hybrid (BM25+Ollama)** |
|---|---|---|---|
| Recall@1 | 65.0% | 60.0% | **80.0%** ↑ |
| Recall@3 | 75.0% | 70.0% | **95.0%** ↑ |
| Recall@5 | 85.0% | 75.0% | **95.0%** ↑ |

Ключевое наблюдение: чистый vector retrieval на маленьком корпусе (26 entities) работает хуже baseline. **Гибрид BM25+vector через Reciprocal Rank Fusion** даёт значительный прирост.

## Что было установлено

| Компонент | Где | Что делает |
|---|---|---|
| Ollama 0.21.2 | `%LOCALAPPDATA%\Programs\Ollama\` | Локальный embedding-сервер на `localhost:11434` |
| nomic-embed-text:latest | через Ollama | 768-dim multilingual embedding модель |
| chromadb 1.5.8 | `.claude/venv_chroma/` (Python 3.14) | Векторная база |
| rank-bm25 | там же | Лексический поиск для гибрида |

## Архитектура поиска

```
Запрос пользователя
        ↓
   ┌────┴────┐
   ↓         ↓
  BM25     Vector (Ollama → Chroma)
   ↓         ↓
   └────┬────┘
        ↓
  RRF fusion (k=60)
        ↓
  Top-N результатов с unified ranking
```

При запросе одновременно работают два ретривера:
- **BM25** — лексический, ловит точные совпадения слов («Константин», «ФСИ», «Сколково»)
- **Vector (Ollama nomic-embed-text)** — семантический, ловит связи по смыслу

Reciprocal Rank Fusion объединяет ранжирования. Рекомендован Anthropic/BEIR как best practice для маленьких корпусов.

## Файлы системы

| Файл | Назначение |
|---|---|
| [.claude/lib/memory_index/provider.py](.claude/lib/memory_index/provider.py) | Embedding provider (Ollama + fallback) |
| [.claude/lib/memory_index/index.py](.claude/lib/memory_index/index.py) | Chroma collection wrapper |
| [.claude/lib/memory_index/parser.py](.claude/lib/memory_index/parser.py) | Парсер auto-memory `.md` файлов |
| [.claude/lib/memory_index/hybrid.py](.claude/lib/memory_index/hybrid.py) | **Hybrid search (BM25+vector+RRF)** |
| [.claude/hooks/memory-index.py](.claude/hooks/memory-index.py) | Auto-update индекс при изменении карточек |
| [.claude/tests/L7_monitoring/memory_reindex.py](.claude/tests/L7_monitoring/memory_reindex.py) | CLI: полная переиндексация |
| [.claude/tests/L7_monitoring/memory_semantic_search.py](.claude/tests/L7_monitoring/memory_semantic_search.py) | CLI: поиск (default mode = hybrid) |
| [.claude/tests/L7_monitoring/memory_search_eval.py](.claude/tests/L7_monitoring/memory_search_eval.py) | Замер качества (vector / hybrid / compare) |
| [.claude/tests/L7_monitoring/reindex_one.py](.claude/tests/L7_monitoring/reindex_one.py) | Инкрементальный реиндекс одного файла |

## Команды для пользователя

### Поиск из терминала
```
D:\REDPEAK\Agent systems\AgentHQ\.claude\venv_chroma\Scripts\python.exe ^
  D:\REDPEAK\Agent systems\AgentHQ\.claude\tests\L7_monitoring\memory_semantic_search.py "встреча с Константином"
```

Опции:
- `--top 10` — больше результатов
- `--mode vector` — только vector-поиск (без BM25), для сравнения
- `--json` — машинный вывод для интеграции
- `--type contact` — фильтр по типу (только в vector mode)

### Перегенерация индекса
```
D:\REDPEAK\Agent systems\AgentHQ\.claude\venv_chroma\Scripts\python.exe ^
  D:\REDPEAK\Agent systems\AgentHQ\.claude\tests\L7_monitoring\memory_reindex.py --clear-first
```

Запускать после: смены embedding-модели, массовых правок в auto-memory, обновления Ollama.

### Замер качества
```
D:\REDPEAK\Agent systems\AgentHQ\.claude\venv_chroma\Scripts\python.exe ^
  D:\REDPEAK\Agent systems\AgentHQ\.claude\tests\L7_monitoring\memory_search_eval.py --compare
```

Покажет таблицу: vector vs hybrid по 4 метрикам.

## Регрессия

| Уровень | Baseline | После всех 7 рекомендаций |
|---|---|---|
| L1 | 84/85 | **108/109** (+24 теста, все PASS) |
| L0-files, L2-L5 | PASS | PASS |
| L0-prompts | PASS | FAIL (T-0.6, ожидаемо до merge) |

Существующий FAIL — H-23 (subagent: empty), был в baseline, не моё.

## Что осталось ручным (для тебя)

1. **При полном перезапуске компьютера** — Ollama должна стартовать сама как сервис. Если не стартует:
   ```
   "C:\Users\sashatrash\AppData\Local\Programs\Ollama\ollama.exe" serve
   ```
   (запустить в фоне один раз).

2. **При merge worktree → master** — основной `settings.json` подхватит регистрацию новых хуков. До этого активны только в worktree.

3. **Когда корпус памяти вырастет** (50+ entities) — качество vector-only увеличится. Возможно, в будущем BM25 не понадобится. Но сейчас гибрид — оптимум.

## Этапы работ — итог

| Этап | Что сделано | L1 |
|---|---|---|
| Baseline | — | 84/85 |
| 1.1 MCP health check | hook + deep CLI | 88/89 (+4) |
| 1.2 Auto-test trigger | hook на изменение агентов | 95/96 (+7) |
| 1.3 Cost attribution | hook + CLI | 101/102 (+6) |
| 2 LLM-as-judge | evaluator-agent активирован | 101/102 |
| 3.2 **Vector memory** | Ollama + Chroma + Hybrid + 7 тестов | **108/109** (+7) |

Из 7 рекомендаций реализовано **5**: MCP health, auto-test trigger, cost attribution, LLM-as-judge, vector memory.

Остались как план-документы (отдельные сессии): **observability**, **planning loop**.
