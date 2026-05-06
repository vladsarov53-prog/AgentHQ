---
name: claude-api
description: Разработка приложений с Claude API, Anthropic SDK, Agent SDK. Используй когда код импортирует `anthropic`/`@anthropic-ai/sdk`/`claude_agent_sdk`, или когда пользователь просит использовать Claude API, Anthropic SDKs, Agent SDK, tool use, structured outputs. НЕ ИСПОЛЬЗУЙ когда код работает с openai или другими AI SDK.
---

# Разработка приложений с Claude API

Этот скилл помогает строить LLM-приложения на Claude API. Поддерживает Python, TypeScript и другие языки.

## Когда использовать

- Код импортирует `anthropic`, `@anthropic-ai/sdk`, `claude_agent_sdk`
- Нужно интегрировать Claude в продукт RedPeak
- Разработка AI-агентов, tool use, structured outputs
- Работа с Agent SDK

## Три уровня интеграции

### 1. Один вызов API
Классификация, суммаризация, извлечение данных, Q&A.

### 2. Workflow (пайплайн)
Многошаговые цепочки с tool use под контролем кода.

### 3. Агент
Автономный агент с инструментами и принятием решений.

## Модели (актуально на 2026-02)

| Модель | Model ID | Контекст | Input $/1M | Output $/1M |
|---|---|---|---|---|
| Claude Opus 4.6 | `claude-opus-4-6` | 200K (1M beta) | $5.00 | $25.00 |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | 200K (1M beta) | $3.00 | $15.00 |
| Claude Haiku 4.5 | `claude-haiku-4-5` | 200K | $1.00 | $5.00 |

Всегда используй точные model ID из таблицы. Не добавляй суффиксы дат.

## Конфигурация по умолчанию

- Модель: `claude-opus-4-6` (по умолчанию, если не указано иное)
- Thinking: `{"type": "adaptive"}` - Claude сам решает когда и сколько думать. `budget_tokens` устарел на Opus 4.6 и Sonnet 4.6.
- Effort: `output_config: {effort: "low"|"medium"|"high"|"max"}` - контроль глубины. `max` только для Opus 4.6.
- Streaming: включен для длинных ввода/вывода (предотвращает таймауты). Для 128K output обязателен.
- Compaction: beta, для длинных разговоров. Авто-суммаризация при приближении к 150K токенов.

## Ключевые возможности

| Возможность | Описание |
|---|---|
| Tool use | Вызов функций, tool runner для автоматического цикла |
| Structured outputs | `output_config: {format: {...}}` (не `output_format` - устарел) |
| Prompt caching | `cache_control: {type: "ephemeral"}`, max 4 breakpoints, min ~1024 токенов |
| Batch API | Массовая обработка (50% скидка, до 24ч) |
| Extended thinking | Adaptive thinking на Opus/Sonnet 4.6, budget_tokens на старых моделях |
| Agent SDK | Python/TS, встроенные file/web/terminal, MCP, permissions |
| Compaction | Beta, авто-суммаризация для длинных разговоров |
| Files API | Загрузка файлов для переиспользования в нескольких запросах |

## Частые ошибки

- Не используй `budget_tokens` на Opus 4.6 / Sonnet 4.6 - используй adaptive thinking
- Не используй prefill (последнее assistant-сообщение) на Opus 4.6 - вернёт 400
- Не занижай `max_tokens`: ~16000 для non-streaming, ~64000 для streaming
- Tool call JSON: всегда парси через `json.loads()` / `JSON.parse()`, не string matching
- Используй SDK типы (`Anthropic.MessageParam`, `Anthropic.Tool`), не свои интерфейсы

## Быстрый старт

### Python
```python
import anthropic

client = anthropic.Anthropic()
message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Привет!"}]
)
```

### TypeScript
```typescript
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();
const message = await client.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 1024,
    messages: [{ role: "user", content: "Привет!" }],
});
```

## Tool Use (function calling)

```python
tools = [{
    "name": "get_weather",
    "description": "Получить погоду в городе",
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "Город"}
        },
        "required": ["location"]
    }
}]

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "Какая погода в Москве?"}]
)
```

## Agent SDK

```python
from claude_agent_sdk import Agent

agent = Agent(
    model="claude-sonnet-4-6",
    tools=["file", "web", "terminal"],
    system="Ты помощник разработчика."
)
result = agent.run("Проанализируй этот код и предложи улучшения")
```

## Рекомендации для RedPeak

- Для CAD-модуля: structured outputs для извлечения параметров из чертежей
- Для rule-based системы: tool use для вызова расчётных функций
- Для пользовательского интерфейса: streaming для отзывчивого UX
- Для batch-обработки: Batch API для массового анализа документов

## Ссылки

- Документация: https://docs.anthropic.com
- SDK Python: https://github.com/anthropics/anthropic-sdk-python
- SDK TypeScript: https://github.com/anthropics/anthropic-sdk-typescript
- Agent SDK: https://github.com/anthropics/claude-code-sdk
