"""Нейтральная модель экрана: текст + сетка кнопок.

Транспорт (Max, Telegram) превращает Screen в свою клавиатуру.
"""
from dataclasses import dataclass, field
from typing import List, Optional

# Max принимает до 7 кнопок в ряду (8 → 400 errors.maxRowSize) и до 30 рядов;
# рядов держим не больше 15, чтобы поле влезало в экран телефона
MAX_COLS = 7
MAX_ROWS = 15
MAX_DATA_LEN = 256
MAX_TEXT_LEN = 64


@dataclass(frozen=True)
class Button:
    text: str
    data: str


@dataclass
class Screen:
    text: str
    rows: List[List[Button]] = field(default_factory=list)

    def validate(self) -> None:
        if len(self.rows) > MAX_ROWS:
            raise ValueError(f"слишком много рядов: {len(self.rows)} > {MAX_ROWS}")
        for row in self.rows:
            if not row or len(row) > MAX_COLS:
                raise ValueError(f"ряд из {len(row)} кнопок, допустимо 1..{MAX_COLS}")
            for b in row:
                if not b.text or len(b.text) > MAX_TEXT_LEN:
                    raise ValueError(f"недопустимый текст кнопки: {b.text!r}")
                if len(b.data) > MAX_DATA_LEN:
                    raise ValueError(f"payload длиннее {MAX_DATA_LEN}: {b.data!r}")


@dataclass
class Reply:
    """Ответ на действие пользователя.

    screen=None — сообщение не меняется, только всплывающее уведомление note.
    """
    screen: Optional[Screen] = None
    note: Optional[str] = None


def data(*parts) -> str:
    return ":".join(str(p) for p in parts)
