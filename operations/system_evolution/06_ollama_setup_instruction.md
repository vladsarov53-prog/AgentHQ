# Установка Ollama — пошагово

**Когда делать:** в любой удобный момент. Установка не зависит от Claude и не блокирует работу системы. Без Ollama векторный поиск работает, но качество на русском низкое (Recall@3 = 75%, должно быть 90%+ с Ollama).

**Время:** 5–10 минут включая загрузку модели.
**Место на диске:** ~700 МБ суммарно (программа + модель).
**Память в фоне:** ~500 МБ RAM пока работает (можно остановить когда не нужно).

---

## Шаг 1. Скачать установщик

Открой: <https://ollama.com/download/windows>

Скачается файл `OllamaSetup.exe` (~150 МБ).

## Шаг 2. Установить

Запусти `OllamaSetup.exe`. Появится окно UAC, согласись. Установщик не задаёт вопросов, ставится в стандартное место (`%LOCALAPPDATA%\Programs\Ollama`). После установки Ollama сама запустится и появится в трее (значок ламы).

## Шаг 3. Проверить что работает

Открой PowerShell или обычный терминал, выполни:

```
ollama --version
```

Должно выйти что-то вроде `ollama version 0.x.x`. Если видно — всё ок.

## Шаг 4. Скачать модель эмбеддингов

```
ollama pull nomic-embed-text
```

Это скачает ~270 МБ (один раз). После завершения проверь:

```
ollama list
```

В списке должна появиться `nomic-embed-text:latest`.

## Шаг 5. Проверить что система видит Ollama

В терминале:

```
D:\REDPEAK\Agent systems\AgentHQ\.claude\venv_chroma\Scripts\python.exe -m memory_index.provider
```

Должно вывести:
```
Embedding: Ollama (nomic-embed-text, multilingual, ~768-dim)
Embedding получен, размерность: 768
```

Если видишь это — всё работает.

## Шаг 6. Перегенерировать индекс с правильной моделью

Старый индекс был построен встроенной Chroma-моделью (английская, плохое качество на русском). Перегенерируем под Ollama:

```
D:\REDPEAK\Agent systems\AgentHQ\.claude\venv_chroma\Scripts\python.exe D:\REDPEAK\Agent systems\AgentHQ\.claude\tests\L7_monitoring\memory_reindex.py --clear-first
```

Займёт ~30 секунд (26 entities × ~1с на embedding через Ollama).

## Шаг 7. Замерить качество

```
D:\REDPEAK\Agent systems\AgentHQ\.claude\venv_chroma\Scripts\python.exe D:\REDPEAK\Agent systems\AgentHQ\.claude\tests\L7_monitoring\memory_search_eval.py
```

Ожидаемый результат:
- **Recall@3 ≥ 85%** (отлично) или **≥ 75%** (приемлемо)
- T-1 «встреча с Константином» должен теперь правильно находить `contact_konstantin` в топ-1

Если Recall@3 < 75% — что-то не так, напиши мне в новой сессии, разберусь.

---

## Что проверить если что-то не работает

### Шаг 3 не показывает версию
- Ollama не установилась. Перезагрузи компьютер, попробуй ещё раз.
- Или путь не в PATH. Откройте `%LOCALAPPDATA%\Programs\Ollama\ollama.exe` напрямую.

### Шаг 4 даёт ошибку «cannot connect»
- Ollama сервис не запущен. Проверь трей — должна быть иконка ламы.
- Если нет: запусти `ollama serve` в одном терминале и `ollama pull ...` в другом.

### Шаг 5 говорит «Ollama недоступна»
- Файервол блокирует localhost:11434. Разреши.
- Или Ollama слушает на другом порту: `netstat -an | findstr 11434` → если ничего, она не запущена.

### Шаг 7 даёт Recall@3 < 75%
- Возможно, не сделан Шаг 6 (перегенерация индекса) — старый индекс с английской моделью даёт плохие результаты.
- Проверь что в выводе `memory_search_eval.py` пишет `Embedding mode: ollama`. Если `chroma_default` — Ollama не поднялась, провайдер не подключился.

---

## Что эта установка даёт системе

После выполнения всех 7 шагов:

1. **Семантический поиск работает на русском нормально** — система понимает что «встреча с Константином» = `contact_konstantin`, даже если слова «встреча» в карточке нет.
2. **Hook индексирует автоматически** — при изменении любой карточки в auto-memory индекс обновляется в фоне (~1 секунда).
3. **CLI для ручного поиска**:
   ```
   D:\REDPEAK\Agent systems\AgentHQ\.claude\venv_chroma\Scripts\python.exe D:\REDPEAK\Agent systems\AgentHQ\.claude\tests\L7_monitoring\memory_semantic_search.py "твой запрос"
   ```
4. **Embeddings локально** — данные не уходят к третьим лицам.

---

## Откат, если не понравится

```
# 1. Удалить Ollama
%LOCALAPPDATA%\Programs\Ollama\uninstall.exe

# 2. Удалить индекс
rmdir /S /Q "D:\REDPEAK\Agent systems\AgentHQ\memory\chroma_db"

# 3. Удалить venv
rmdir /S /Q "D:\REDPEAK\Agent systems\AgentHQ\.claude\venv_chroma"

# 4. Убрать memory-index.py из settings.json (вручную)
```

Никакие entities в auto-memory не пострадают — индекс это надстройка, не сама память.

---

## После установки — пиши

Когда сделаешь шаги 1–6, открой новую сессию с темой «Векторная память — после установки Ollama» и скажи что готово. Я подключу субагентов к семантическому поиску и проведу финальный регрессионный прогон.
