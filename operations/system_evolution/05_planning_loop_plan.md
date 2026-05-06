# Этап 3.3 — Planning Loop / явный state machine

**Статус:** план, требует отдельной сессии. **Самый высокий риск регрессии — менять архитектуру диспетчера.**

## Задача

Сейчас в [CLAUDE.md](CLAUDE.md) есть «Единый цикл работы» из 11 шагов, но это инструкция для модели, не явный state machine. Лидеры (Anthropic ReAct, Google Tree-of-Thoughts, SWE-agent) делают planning отдельным этапом со state-tracking.

## Что хотим получить

Явный плановщик, который **до** маршрутизации:
1. Парсит запрос → формирует **structured plan**: подзадачи, порядок, зависимости, ожидаемые источники
2. Показывает план пользователю → ждёт подтверждения
3. Выполняет шаг за шагом, каждый шаг логирует
4. Может пересмотреть план при появлении новой информации
5. Итоговый отчёт включает все принятые решения и почему

## Опции (3 варианта)

### Вариант А: Внешний planner-agent (новый субагент)
- Создать `planner-agent.md` — отдельный субагент с одной задачей: разложить запрос на план
- Диспетчер сначала вызывает planner, потом выполняет.
- **Плюсы:** изоляция, тестируется отдельно, обратимо (просто не вызывать)
- **Минусы:** дополнительный hop = +latency и +cost
- **Источник:** Anthropic «Orchestrator-Workers» pattern.

### Вариант Б: Расширение CLAUDE.md (planning встроен в диспетчер)
- Добавить раздел «Planning Phase» — обязательный perform до маршрутизации для задач с >1 шагом
- TodoWrite tool уже даёт частичное решение
- **Плюсы:** zero overhead, всё в инструкциях
- **Минусы:** может игнорироваться моделью (видели на практике, что инструкции из CLAUDE.md не всегда соблюдаются)

### Вариант В: Hook-driven planner (UserPromptSubmit hook)
- Hook парсит запрос, классифицирует сложность (1-step / N-step), при N-step требует TodoWrite в первом ответе
- Stop-hook проверяет, что TodoWrite был использован для сложных запросов
- **Плюсы:** машинная проверка, не зависит от модели
- **Минусы:** false positives (классификация сложности нетривиальна)

## Рекомендация

**Комбинация Б + В:**
- В CLAUDE.md явный раздел «Planning Phase» — что обязательно для multi-step задач
- Soft hook через UserPromptSubmit, который **подсказывает** в additionalContext «эта задача выглядит сложной (N+ шагов) — начни с TodoWrite»
- НЕ блокирующий (warning, не error)
- Постепенно: если warnings ловит false-positives — корректируем эвристику; если model игнорирует — усиливаем до блокировки

Аргументация:
- Не плодить агентов без необходимости
- Hook-based подход уже показал себя в существующих гватрейлах
- TodoWrite — нативный инструмент Claude Code, не надо изобретать свой state machine
- Эволюционная стратегия: warning → enforcement при подтверждении эффекта

## Что нужно для реализации (отдельная сессия, ~3 часа)

### Шаг 1: Hook
- `.claude/hooks/planning-prompt.py` (UserPromptSubmit):
  - Эвристика сложности: длина prompt, наличие "и", "затем", чисел вроде "три задачи", упоминание нескольких subagent-доменов
  - Если сложно: `additionalContext` = «Запрос выглядит сложным. Используй TodoWrite перед маршрутизацией.»

### Шаг 2: Stop-check
- В существующий `verification-gate.py` добавить:
  - Если в session history был сложный prompt И TodoWrite не вызывался → warning в stderr
  - Не блокирующее, soft enforcement

### Шаг 3: CLAUDE.md
- Раздел «Planning Phase» перед «Маршрутизация»
- Триггеры: задача с >2 артефактами, кросс-ролевая, требует расчётов + документа
- Шаблон плана (что должно быть в TodoWrite)

### Шаг 4: Тесты
- L1: 5 кейсов на planning-prompt.py (простой / сложный / multi-domain / edge-case)
- L3: добавить категорию «complex tasks» в routing_cases.json — проверять что система формирует план

### Шаг 5: Регрессия
- Сравнить calibration_log за 2 недели до и после: уменьшается ли число `incomplete_task` ошибок?
- Метрика успеха: -30% incomplete_task за 2 недели

## Риски

- **Очень высокий:** изменение CLAUDE.md = изменение всех взаимодействий. Любая ошибка в формулировке планинг-фазы скажется на всех задачах.
- **Высокий:** false positives — простые задачи будут лишний раз триггерить warning, раздражение.
- **Средний:** TodoWrite не всегда нужен — для коротких задач это overhead.

## Стоп-точки

- Перед изменением CLAUDE.md (раздел Planning Phase) — explicit confirmation
- Перед слиянием worktree → master — A/B-тестирование на реальных задачах за неделю
- Если за 2 недели metric «incomplete_task» не улучшится — откат

## Acceptance Criteria

- [ ] Hook ловит >70% сложных запросов как «требует plan» (точность на тестовом наборе из 30 prompt'ов)
- [ ] Hook не триггерит false-positive чаще, чем 1 из 10 простых запросов
- [ ] L3 routing tests показывают новую категорию «multi-step with plan» — все PASS
- [ ] Calibration log за 2 недели показывает -30% incomplete_task (или больше) → закрепляем; меньше → итерация эвристики
- [ ] Регрессия L0-L5: не хуже текущего baseline (101/102 L1 + 6/7 уровней)

## Источники [МОЯ ИНТЕРПРЕТАЦИЯ из публичной документации]

- Anthropic «Building Effective Agents» — Orchestrator-Workers, Planner-Executor patterns
- Google DeepMind ReAct paper — explicit reasoning steps
- Tree-of-Thoughts (Princeton/Google) — branching planning
- SWE-agent (Princeton) — agent-computer interface for planning
- TodoWrite tool description (Claude Code documentation)
