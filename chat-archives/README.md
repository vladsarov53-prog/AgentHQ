# Chat Archives

Ежедневные архивы транскриптов Claude Code сессий.

## Структура

```
chat-archives/
  raw/                     ← сырые .jsonl, залитые Stop-хуком после каждой сессии
    YYYY-MM-DD/
      <session_id>.jsonl
  YYYY-MM-DD.tar.gz        ← скомпрессированный архив за день (создаёт remote routine)
  index.md                 ← индекс всех архивов
  README.md
```

## Как это работает

1. **Stop-hook** (`chat-archive-push.py`) при завершении каждой сессии Claude Code копирует
   транскрипт в `raw/YYYY-MM-DD/` и пушит в Git.

2. **Remote routine «RedPeak HQ — Daily Backup»** (19:00 МСК) упаковывает папки из `raw/`
   в `.tar.gz`, удаляет сырые файлы, чистит архивы старше 90 дней.

## Восстановление

```bash
git clone https://github.com/vladsarov53-prog/AgentHQ.git
cd AgentHQ
# Извлечь конкретный день:
tar -xzf chat-archives/YYYY-MM-DD.tar.gz
# Файлы .jsonl можно читать через: jq . <session_id>.jsonl
```

## Хранение

Архивы хранятся **90 дней**. Старые удаляются автоматически.
