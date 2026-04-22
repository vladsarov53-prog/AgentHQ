---
name: webapp-testing
description: Тестирование веб-приложений через Playwright. Используй когда нужно протестировать UI, проверить функциональность фронтенда, отладить поведение интерфейса, сделать скриншоты страниц, прочитать логи браузера, автоматизировать тестирование веб-приложения.
---

# Тестирование веб-приложений (Playwright)

Инструментарий для автоматизации взаимодействия с веб-приложениями и их тестирования через Python Playwright.

## Возможности

- Проверка функциональности UI
- Отладка поведения интерфейса
- Скриншоты состояний приложения
- Чтение логов браузера
- End-to-end тестирование

## Подход: Reconnaissance-Then-Action

1. Навигация + wait for `networkidle`
2. Скриншот или инспекция DOM
3. Определение CSS/role/text селекторов из рендера
4. Выполнение действий по найденным селекторам

## Быстрый старт

### Установка
```bash
pip install playwright
playwright install chromium
```

### Базовый скрипт
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:5173')
    page.wait_for_load_state('networkidle')  # Критически важно!

    # Скриншот
    page.screenshot(path='screenshot.png')

    # Клик по элементу
    page.click('button:text("Войти")')

    # Заполнение формы
    page.fill('#email', 'test@example.com')

    # Проверка текста
    assert page.text_content('.status') == 'Готово'

    browser.close()
```

### Запуск с сервером
```bash
# Запуск сервера + тестов
python scripts/with_server.py --server "npm run dev" --port 5173 -- python test_app.py
```

## Best Practices

- Всегда `wait_for_load_state('networkidle')` перед инспекцией
- Описательные селекторы: `text=`, `role=`, CSS, IDs
- `page.wait_for_selector()` для динамических элементов
- Headless=True для CI, headless=False для отладки
- Скриншоты на каждом шаге при отладке

## Паттерны тестирования

### Smoke test
```python
def test_homepage_loads(page):
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle')
    assert page.title() != ''
    assert page.query_selector('main') is not None
```

### Form submission
```python
def test_login_flow(page):
    page.goto(f'{BASE_URL}/login')
    page.fill('[name="email"]', 'user@test.com')
    page.fill('[name="password"]', 'password123')
    page.click('button[type="submit"]')
    page.wait_for_url(f'{BASE_URL}/dashboard')
    assert 'Dashboard' in page.text_content('h1')
```

## Вспомогательные файлы

- **scripts/with_server.py** - Запуск серверов + выполнение команды + автоочистка. Запусти с `--help` для справки.
- **examples/element_discovery.py** - Обнаружение кнопок, ссылок и полей ввода на странице
- **examples/console_logging.py** - Перехват логов браузерной консоли

Используй скрипты как чёрные ящики. Не читай исходники, пока не попробуешь `--help`.

## Для RedPeak

- Тестирование веб-интерфейса CAD-анализатора
- Проверка дашбордов и визуализаций
- Автоматизация smoke tests для демо-версий
- Скриншоты для отчётов ФСИ
