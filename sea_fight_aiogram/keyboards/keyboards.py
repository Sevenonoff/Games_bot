from typing import List, Dict, Any
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.i18n import get_translation
from config import ROWS, COLS, EMPTY, SHIP, BANG, BIGBANG, MISS


class ButtonFactory:
    def create_button(self, text_key: str, callback_data: str,
                      language_code: str, **format_kwargs) -> InlineKeyboardButton:
        """Создать кнопку с переводом"""
        text = get_translation(language_code, text_key)

        if format_kwargs:
            text = text.format(**format_kwargs)

        return InlineKeyboardButton(text=text, callback_data=callback_data)


class KeyboardBuilder:
    def __init__(self, button_factory: ButtonFactory):
        self.button_factory = button_factory

    def create_name_keyboard(self, language_code: str,
                              current_user_info: Dict[str, Any]) -> InlineKeyboardMarkup:
        """Создать клавиатуру выбора имени для лидерборда"""
        keyboard: List[List[InlineKeyboardButton]] = []
        row: List[InlineKeyboardButton] = []

        name = current_user_info.get('leaderboard_name') or current_user_info.get('first_name', '')
        if name:
            callback_data = ('name_tg' if not current_user_info.get('leaderboard_name')
                            else 'name_lastused')
            button = self.button_factory.create_button(
                'text_use_name',
                callback_data,
                language_code=language_code,
                name=name
            )
            row.append(button)

        row.append(self.button_factory.create_button(
            'text_use_other_name',
            'name_new',
            language_code
        ))
        keyboard.append(row)

        keyboard.append([
            self.button_factory.create_button(
                'text_leaderboard_skip',
                'leaderboard_skip',
                language_code
            )
        ])

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    def create_main_keyboard(self, language_code: str) -> InlineKeyboardMarkup:
        """Создать главное меню"""
        keyboard = [
            [self.button_factory.create_button(
                'btn_single_game',
                'newgame',
                language_code
            )],
            [self.button_factory.create_button(
                'btn_multiplayer',
                'multiplayer_start',
                language_code
            )],
            [self.button_factory.create_button(
                'btn_leaderboard',
                'leaderboard_show',
                language_code
            )]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    def create_sea_fight_keyboard(self, player_board: Any, callback_prefix: str = 'fire') -> InlineKeyboardMarkup:
        """Создать игровое поле морского боя"""
        keyboard = []
        for y in range(player_board.rows):
            row = []
            for x in range(player_board.cols):
                sym = player_board.board[y][x]
                row.append(InlineKeyboardButton(
                    text=sym,
                    callback_data=f'{callback_prefix}_{x}_{y}'
                ))
            keyboard.append(row)
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    def create_ship_set_keyboard(self, language_code: str) -> InlineKeyboardMarkup:
        """Создать клавиатуру выбора набора кораблей"""
        keyboard = [
            [self.button_factory.create_button(
                'ship_set_full',
                'shipset_full',
                language_code
            )],
            [self.button_factory.create_button(
                'ship_set_reduced',
                'shipset_reduced',
                language_code
            )],
            [self.button_factory.create_button(
                'btn_cancel',
                'mp_cancel',
                language_code
            )],
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    def create_leaderboard_type_keyboard(self, language_code: str) -> InlineKeyboardMarkup:
        """Создать клавиатуру выбора типа лидерборда"""
        keyboard = [
            [self.button_factory.create_button(
                'leaderboard_solo_full',
                'lb_type_solo_full',
                language_code
            )],
            [self.button_factory.create_button(
                'leaderboard_solo_reduced',
                'lb_type_solo_reduced',
                language_code
            )],
            [self.button_factory.create_button(
                'leaderboard_mp_full',
                'lb_type_mp_full',
                language_code
            )],
            [self.button_factory.create_button(
                'leaderboard_mp_reduced',
                'lb_type_mp_reduced',
                language_code
            )],
            [self.button_factory.create_button(
                'btn_cancel',
                'menu',
                language_code
            )],
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)


# Устаревшие функции для совместимости
def create_main_keyboard(language_code: str) -> InlineKeyboardMarkup:
    """Создать главное меню (устаревшее)"""
    keyboard = [
        [InlineKeyboardButton(
            text=get_translation(language_code, 'btn_new_game'),
            callback_data='newgame'
        )],
        [InlineKeyboardButton(
            text=get_translation(language_code, 'btn_leaderboard'),
            callback_data='leaderboard_show'
        )]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_sea_fight_keyboard(player_board: Any) -> InlineKeyboardMarkup:
    """Создать игровое поле (устаревшее)"""
    keyboard = []
    y = 0
    for line in player_board:
        row = []
        x = 0
        for sym in line:
            row.append(InlineKeyboardButton(
                text=sym,
                callback_data=f'fire_{x}_{y}'
            ))
            x += 1
        keyboard.append(row)
        y += 1
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_name_keyboard(language_code: str,
                          current_user_info: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Создать клавиатуру выбора имени (устаревшее)"""
    keyboard = []
    row = []

    if not current_user_info.get('leaderboard_name'):
        name = current_user_info.get('first_name', '')
        if name:
            row.append(InlineKeyboardButton(
                text=f"{get_translation(language_code, 'text_use_name')} '{name}'",
                callback_data='name_tg'
            ))
    else:
        name = current_user_info['leaderboard_name']
        row.append(InlineKeyboardButton(
            text=f"{get_translation(language_code, 'text_use_name')} '{name}'",
            callback_data='name_lastused'
        ))

    row.append(InlineKeyboardButton(
        text=get_translation(language_code, 'text_use_other_name'),
        callback_data='name_new'
    ))

    keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton(
            text=get_translation(language_code, 'text_leaderboard_skip'),
            callback_data='leaderboard_skip'
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
