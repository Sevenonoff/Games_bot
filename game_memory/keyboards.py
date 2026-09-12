from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu() -> InlineKeyboardMarkup:
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🎮 Развитие памяти",
        callback_data="game_memory"
    ))
    # Можно добавить другие игры позже
    builder.add(InlineKeyboardButton(
        text="📊 Статистика",
        callback_data="stats"
    ))
    builder.adjust(1)
    return builder.as_markup()


def create_memory_field(
        size: int = 8,
        blue_positions: set = None,
        clicked_positions: dict = None,
        game_over: bool = False
) -> InlineKeyboardMarkup:
    """
    Создает игровое поле для игры на память

    Args:
        size: размер поля (size x size)
        blue_positions: множество с позициями синих клеток {(row, col), ...}
        clicked_positions: словарь с нажатыми позициями {(row, col): is_correct}
        game_over: режим окончания игры (показываем все синие клетки)
    """
    if blue_positions is None:
        blue_positions = set()
    if clicked_positions is None:
        clicked_positions = {}

    builder = InlineKeyboardBuilder()

    for row in range(size):
        for col in range(size):
            pos = (row, col)
            if pos in clicked_positions:
                # Клетка была нажата
                if clicked_positions[pos]:  # Правильно
                    text = "🔵"
                else:  # Неправильно
                    text = "🔴"
            elif game_over and pos in blue_positions:
                # Показываем неотгаданные синие клетки
                text = "🔵"
            else:
                text = "⬛"

            builder.add(InlineKeyboardButton(
                text=text,
                callback_data=f"cell_{row}_{col}"
            ))

    # Дополнительные кнопки (9-й ряд)
    if game_over:
        builder.add(InlineKeyboardButton(
            text="🔁 Ещё раз",
            callback_data="retry"
        ))
    else:
        builder.add(InlineKeyboardButton(
            text="🏠 В меню",
            callback_data="menu"
        ))

    builder.adjust(size, size, 1)  # 8x8 + 1 кнопка
    return builder.as_markup()