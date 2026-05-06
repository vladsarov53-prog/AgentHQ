from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .formatter import TAG_LABELS


def tags_keyboard(selected: list[str] | None = None) -> InlineKeyboardMarkup:
    selected = selected or []
    buttons = []

    for tag_id, label in TAG_LABELS.items():
        marker = "[+] " if tag_id in selected else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{marker}{label}",
                callback_data=f"tag:{tag_id}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="Все темы", callback_data="tag:all"),
        InlineKeyboardButton(text="Готово", callback_data="tag:done"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def settings_keyboard(
    instant_enabled: bool,
    digest_enabled: bool,
) -> InlineKeyboardMarkup:
    instant_text = "[+] Мгновенные" if instant_enabled else "[-] Мгновенные"
    digest_text = "[+] Дайджест" if digest_enabled else "[-] Дайджест"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=instant_text, callback_data="set:instant")],
        [InlineKeyboardButton(text=digest_text, callback_data="set:digest")],
        [InlineKeyboardButton(text="Фильтр тегов", callback_data="set:tags")],
    ])
