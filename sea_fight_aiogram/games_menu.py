"""Игры ядра games_core в Telegram: payload'ы, лимиты клавиатуры, имя игрока.

Без aiogram — модуль проверяется тестами ядра (.venv). Связка с aiogram — games_tg.py.

С 2.0.0 все игры, включая морской бой и бой с другом, — из ядра, как в Max.
Кнопки ядра уходят в Telegram с префиксом «g:»: по нему старые кнопки aiogram-боя
(fire_…, mpfire_…) отличаются от кнопок ядра и получают «кнопка устарела».
"""
from typing import List, Optional, Tuple

from games_core.ui import Screen

PLATFORM = "tg"
PREFIX = "g:"

# Bot API: до 8 кнопок в ряду, до 100 на клавиатуре, callback_data до 64 байт
TG_MAX_COLS = 8
TG_MAX_BUTTONS = 100
TG_MAX_DATA_BYTES = 64


def tg_data(core: str) -> str:
    return PREFIX + core


def core_payload(callback_data: Optional[str]) -> Optional[str]:
    """callback_data кнопки ядра → payload для Manager; None — callback не ядра."""
    if callback_data and callback_data.startswith(PREFIX):
        return callback_data[len(PREFIX):]
    return None


def tg_rows(screen: Screen) -> List[List[Tuple[str, str]]]:
    """Ряды (подпись, callback_data) с проверкой лимитов Telegram."""
    rows = [[(b.text, tg_data(b.data)) for b in row] for row in screen.rows]
    total = sum(len(row) for row in rows)
    if total > TG_MAX_BUTTONS:
        raise ValueError(f"кнопок {total} > {TG_MAX_BUTTONS}")
    for row in rows:
        if not row or len(row) > TG_MAX_COLS:
            raise ValueError(f"ряд из {len(row)} кнопок, допустимо 1..{TG_MAX_COLS}")
        for text, cb in row:
            if len(cb.encode()) > TG_MAX_DATA_BYTES:
                raise ValueError(f"callback_data длиннее {TG_MAX_DATA_BYTES} байт: {cb!r}")
    return rows


def format_player_name(username: Optional[str], first_name: Optional[str],
                       user_id: int) -> str:
    """Имя игрока для таблиц: username → имя из Telegram → числовой id.

    Без «@» — иначе Telegram превращает ник в кликабельную ссылку на профиль.
    """
    if username:
        return username.lstrip('@')
    return first_name or str(user_id)
