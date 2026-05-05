"""
Screenshot Verification Gate Hook (Stop)
Блокирующий: требует визуальной верификации перед завершением задачи,
которая создаёт визуальный артефакт.

Логика:
1. Парсит transcript_path: первый user prompt + Write/Edit/NotebookEdit/Skill tool calls.
2. Определяет task_kind (ui, web, docx, pdf, pptx, xlsx, cad).
3. Проверяет наличие визуальной верификации:
   - Tool call к Chrome MCP / Preview MCP / pdf-viewer MCP / Bash playwright|screenshot
   - Маркер «⚠️ визуально не проверил» в последнем сообщении
4. Если task screenshot-verifiable И верификации нет → exit 2 + причина в stderr.
   Иначе → exit 0.

Источник правила:
- memory/feedback_screenshot_before_done.md
- operations/calibration_log.md: 2026-04-30 (CAD), 2026-05-01 (предупреждение перед захватом),
  2026-05-04 (HUD VoiceTypingRU)
- CLAUDE.md, Verification Gate (шаг 6)
"""

import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _read_input():
    try:
        raw = sys.stdin.buffer.read()
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}


# --- Триггеры task_kind ---

UI_KEYWORDS = re.compile(
    r"(\bui\b|интерфейс|фронтенд|дашборд|лендинг|"
    r"\breact\b|компонент|вёрстк|верстк|панел|окно|\bhud\b|"
    r"кнопк|форм|стилиз|вёрст)",
    re.IGNORECASE,
)
WEB_KEYWORDS = re.compile(
    r"(gmail|hh\.ru|зайди на сайт|отклик на вакансию|"
    r"отправ.*через сайт|форм.*на сайте|заполн.*на сайте|"
    r"\bбраузер\b)",
    re.IGNORECASE,
)

# Расширения файлов → категория
EXT_TO_KIND = {
    ".html": "ui",
    ".htm": "ui",
    ".tsx": "ui",
    ".jsx": "ui",
    ".vue": "ui",
    ".css": "ui",
    ".scss": "ui",
    ".docx": "docx",
    ".pdf": "pdf",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".cdw": "cad",
    ".m3d": "cad",
}

# Скиллы → категория
SKILL_TO_KIND = [
    ("frontend-design", "ui"),
    ("webapp-testing", "ui"),
    ("theme-factory", "ui"),
    ("anthropic-skills:docx", "docx"),
    ("anthropic-skills:pdf", "pdf"),
    ("pdf-viewer", "pdf"),
    ("anthropic-skills:pptx", "pptx"),
    ("anthropic-skills:xlsx", "xlsx"),
]

# Имена tool calls, доказывающих визуальную верификацию
SCREENSHOT_TOOL_PATTERNS = [
    re.compile(r"mcp__Claude_in_Chrome__", re.IGNORECASE),
    re.compile(r"mcp__Claude_Preview__preview_screenshot", re.IGNORECASE),
    re.compile(r"mcp__plugin_pdf-viewer_pdf__display_pdf", re.IGNORECASE),
    re.compile(r"mcp__plugin_pdf-viewer_pdf__submit_page_data", re.IGNORECASE),
    re.compile(r"mcp__plugin_pdf-viewer_pdf__interact", re.IGNORECASE),
    re.compile(r"mcp__Claude_Preview__preview_snapshot", re.IGNORECASE),
]

# Содержимое Bash command, доказывающее screenshot
SCREENSHOT_BASH_PATTERNS = [
    re.compile(r"page\.screenshot\(", re.IGNORECASE),
    re.compile(r"\bscreencapture\b", re.IGNORECASE),
    re.compile(r"playwright", re.IGNORECASE),
    re.compile(r"\.screenshot\(", re.IGNORECASE),
]

# Явный маркер отказа от скриншота (разрешает прохождение)
SKIP_MARKERS = [
    "⚠️ визуально не проверил",
    "визуально не проверил",
    "скриншот невозможен",
    "не удалось сделать скриншот",
    "[визуально не проверено]",
    "визуально не верифицировано",
    "[визуально не проверил]",
    "screenshot невозможен",
]

# Текст для блокирующего сообщения
LABELS = {
    "ui": "UI/фронтенд",
    "web": "веб-задача",
    "docx": "DOCX-документ",
    "pdf": "PDF-документ",
    "pptx": "PPTX-презентация",
    "xlsx": "XLSX-таблица",
    "cad": "CAD-чертёж",
}

INSTRUCTIONS = {
    "ui": "webapp-testing (Playwright page.screenshot) или mcp__Claude_in_Chrome__computer",
    "web": "mcp__Claude_in_Chrome__computer (screenshot вкладки)",
    "docx": "anthropic-skills:docx (рендер) + mcp__Claude_Preview__preview_screenshot",
    "pdf": "mcp__plugin_pdf-viewer_pdf__display_pdf",
    "pptx": "anthropic-skills:pptx (export → png/pdf) + Claude_Preview screenshot",
    "xlsx": "anthropic-skills:xlsx (рендер таблицы) + screenshot",
    "cad": "Скриншот окна КОМПАС (СНАЧАЛА предупреди пользователя — calibration_log 2026-05-01)",
}

MIN_RESPONSE_LENGTH = 20
MAX_TRANSCRIPT_BYTES = 5 * 1024 * 1024  # 5 МБ — защита от гигантских transcripts
RECENT_EVENTS_LIMIT = 200


def parse_transcript(transcript_path):
    """
    Возвращает (first_user_prompt, tool_calls, file_paths).

    tool_calls: list of (tool_name, input_json_str)
    file_paths: list of (path, tool_name) — только из Write/Edit/NotebookEdit
    """
    first_user_prompt = ""
    tool_calls = []
    file_paths = []

    if not transcript_path or not os.path.exists(transcript_path):
        return "", [], []

    try:
        size = os.path.getsize(transcript_path)
        if size > MAX_TRANSCRIPT_BYTES:
            return "", [], []
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return "", [], []

    # Первый user prompt — ищем в начале transcript
    for line in lines[:15]:
        try:
            obj = json.loads(line)
            if obj.get("type") != "user":
                continue
            content = obj.get("message", {}).get("content")
            if isinstance(content, str) and content.strip():
                first_user_prompt = content
                break
            if isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        t = item.get("text", "")
                        if t:
                            texts.append(t)
                if texts:
                    first_user_prompt = "\n".join(texts)
                    break
        except Exception:
            continue

    # Последние N строк — для поиска tool calls
    recent = lines[-RECENT_EVENTS_LIMIT:] if len(lines) > RECENT_EVENTS_LIMIT else lines
    for line in recent:
        try:
            obj = json.loads(line)
            if obj.get("type") != "assistant":
                continue
            content = obj.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "tool_use":
                    continue
                name = item.get("name", "") or ""
                inp = item.get("input", {})
                try:
                    inp_str = json.dumps(inp, ensure_ascii=False)
                except Exception:
                    inp_str = str(inp)
                tool_calls.append((name, inp_str))

                if isinstance(inp, dict) and name in ("Write", "Edit", "NotebookEdit"):
                    fp = inp.get("file_path") or inp.get("notebook_path") or ""
                    if fp:
                        file_paths.append((str(fp), name))
        except Exception:
            continue

    return first_user_prompt, tool_calls, file_paths


def detect_task_kind(user_prompt, tool_calls, file_paths):
    """Возвращает категорию screenshot-verifiable задачи или None."""
    # 1. Расширения файлов из Write/Edit
    for fp, _tool in file_paths:
        fp_lower = fp.lower()
        for ext, kind in EXT_TO_KIND.items():
            if fp_lower.endswith(ext):
                return kind

    # 2. Skill вызовы
    for name, inp_str in tool_calls:
        if name != "Skill":
            continue
        inp_lower = inp_str.lower()
        for skill_marker, kind in SKILL_TO_KIND:
            if skill_marker.lower() in inp_lower:
                return kind

    # 3. PDF создан/сохранён через pdf-viewer plugin
    for name, _ in tool_calls:
        n_lower = name.lower()
        if "pdf-viewer" in n_lower and ("save_pdf" in n_lower or "submit_save_data" in n_lower):
            return "pdf"

    # 4. Ключевые слова user prompt
    if user_prompt:
        if WEB_KEYWORDS.search(user_prompt):
            return "web"
        if UI_KEYWORDS.search(user_prompt):
            return "ui"

    return None


def has_screenshot_evidence(tool_calls, last_message):
    """Был ли скриншот сделан / явный маркер отказа."""
    for name, inp_str in tool_calls:
        for pattern in SCREENSHOT_TOOL_PATTERNS:
            if pattern.search(name):
                return True
        if name == "Bash":
            for pattern in SCREENSHOT_BASH_PATTERNS:
                if pattern.search(inp_str):
                    return True

    msg_lower = (last_message or "").lower()
    for marker in SKIP_MARKERS:
        if marker.lower() in msg_lower:
            return True

    return False


def main():
    input_data = _read_input()
    if not input_data:
        sys.exit(0)

    if input_data.get("stop_hook_active", False):
        sys.exit(0)

    last_message = input_data.get("last_assistant_message", "") or ""
    if len(last_message.strip()) < MIN_RESPONSE_LENGTH:
        sys.exit(0)

    transcript_path = input_data.get("transcript_path", "")
    user_prompt, tool_calls, file_paths = parse_transcript(transcript_path)

    task_kind = detect_task_kind(user_prompt, tool_calls, file_paths)
    if task_kind is None:
        sys.exit(0)

    if has_screenshot_evidence(tool_calls, last_message):
        sys.exit(0)

    label = LABELS.get(task_kind, task_kind)
    instruction = INSTRUCTIONS.get(task_kind, "сделай скриншот")
    print(
        f"Screenshot Gate: задача создаёт визуальный артефакт ({label}). "
        f"Перед заявлением «готово» обязателен скриншот через {instruction} "
        f"и сверка с требованиями. "
        f"Если технически невозможно — добавь в финальный ответ маркер "
        f"«⚠️ визуально не проверил, причина: ...». "
        f"Источник правила: memory/feedback_screenshot_before_done.md, "
        f"calibration_log 2026-05-04.",
        file=sys.stderr,
    )
    sys.stderr.flush()
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
