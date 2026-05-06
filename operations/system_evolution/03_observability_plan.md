# Этап 3.1 — Observability / трейсинг агентов

**Статус:** план, требует отдельной сессии. **Не запускать одновременно с другими этапами.**

## Задача

Дать видимость того, что происходит внутри субагентов: какие файлы читали, какие тесты прогнали, сколько времени, какие ошибки. Сейчас [session-log.py](.claude/hooks/session-log.py) пишет только Write/Edit-события — это <10% от реальной активности.

## Что выбрать (3 варианта)

### Вариант А: Langfuse (open-source, self-hosted)
- **Плюсы:** полноценные traces со span-структурой, free tier, локальный Docker.
- **Минусы:** Docker-зависимость, отдельный сервис, требует SDK-интеграции в каждый хук.
- **Стоимость:** $0 (self-hosted) или $59/мес (cloud).
- **Источник:** langfuse.com, ~6k stars на GitHub.

### Вариант Б: Phoenix Arize (open-source, OpenTelemetry-based)
- **Плюсы:** OpenTelemetry-стандарт, работает с любыми LLM-фреймворками, локальный.
- **Минусы:** нет родной интеграции с Claude Code hooks, нужен middleware.
- **Стоимость:** $0.
- **Источник:** phoenix.arize.com, ~3k stars.

### Вариант В: Своё решение (JSONL + CLI-аналитика)
- **Плюсы:** zero dependencies, полностью локально, формат под твою систему. Уже есть прецедент: [cost_attribution.jsonl](operations/cost_attribution.jsonl).
- **Минусы:** нет UI, надо писать аналитику вручную.
- **Стоимость:** $0.
- **Источник:** [МОЯ ИНТЕРПРЕТАЦИЯ] подход, основанный на принципе "shallow observability" из Google SRE Workbook + личный опыт построения lightweight tracing.

## Рекомендация

**Вариант В для этапа 3.1**, **Вариант А — для этапа 3.2 (если понадобится UI).**

Аргументация:
- Не плодить зависимости пока не доказана необходимость UI
- JSONL-формат уже работает (cost-attribution)
- Можно дописать `agent-trace.py` хук, аналогичный [cost-attribution.py](.claude/hooks/cost-attribution.py)
- При желании потом можно импортировать JSONL в Langfuse

## Что нужно для реализации (отдельная сессия)

1. **Hook:** `agent-trace.py` (PreToolUse + PostToolUse) — пишет в `operations/agent_traces.jsonl`:
   - timestamp, tool_name, tool_input (sanitized), latency_ms, success/error
   - Для Task tool — тот же subagent_type как в cost-attribution
2. **CLI:** `.claude/tests/L7_monitoring/trace_summary.py`:
   - Топ-10 самых медленных вызовов
   - Распределение по типам инструментов
   - Ошибки с группировкой
3. **L1-тесты:** 6-8 кейсов на новый хук (как для других)
4. **Регистрация в settings.json**: PreToolUse + PostToolUse (но только в worktree → merge)
5. **Регрессия:** прогон L0-L5 до и после, сравнение

## Риски

- Hook на КАЖДЫЙ tool call → накладной расход. Нужна асинхронная запись (background thread).
- В sanitized tool_input не должно быть конфиденциальных данных. Hook должен фильтровать `documents/contracts/personal/`.
- JSONL может разрастись — нужна ротация (>10 МБ → archive).

## Acceptance Criteria

- [ ] `agent-trace.py` < 50ms overhead per call (измерить)
- [ ] `trace_summary.py` показывает таблицу за последние 24/7/30 дней
- [ ] Sanitization: 0 утечек паролей/токенов (regex-фильтр)
- [ ] L1 покрытие нового хука: 6+ unit-тестов
- [ ] Регрессия: L1 = 101/102 (или лучше), L0-L5 без регрессии

## Источники [МОЯ ИНТЕРПРЕТАЦИЯ из публичной документации]

- Anthropic «Building Effective Agents» — observability как guardrail
- Google SRE Workbook — shallow vs deep probes
- Langfuse docs — span/trace модель
- OpenTelemetry spec — для вектора Б, если выберем
