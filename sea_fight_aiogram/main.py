import asyncio
import html
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import logging.handlers

from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import (BOT_TOKEN, ROWS, COLS, EMPTY, SHIP, BANG, BIGBANG, MISS,
                    AVAILABLE, BUILDING_SHIP, SHIPS, SHIPS_REDUCED, DELAY)
from database import Database, User
from database.models import LeaderboardEntry
from database.multiplayer_models import MultiplayerGame
from utils.game_logic import GameLogic, Board, check_ship_sunk_on_board, collect_ship_cells
from utils.ship_placement import ManualPlacementLogic
from utils.i18n import get_translation, replace_placeholders
from keyboards import ButtonFactory, KeyboardBuilder
from states import MultiplayerStates, SinglePlayerStates

# Игры ядра (мемо, матрица, башня) — из корня репозитория. append, а не insert:
# корень не должен перекрывать модули бота (config, database, utils)
sys.path.append(str(Path(__file__).resolve().parent.parent))
from games_core.manager import Manager  # noqa: E402
from games_core.storage import Storage  # noqa: E402

import config  # noqa: E402
import games_tg  # noqa: E402
from games_menu import format_player_name  # noqa: E402

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN не задан. Создайте файл .env по образцу .env.example")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Настройка логирования: LOG_FILE — файл с ротацией, иначе stdout
if config.LOG_FILE:
    Path(config.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    _log_handlers = [logging.handlers.RotatingFileHandler(
        config.LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")]
else:
    _log_handlers = [logging.StreamHandler(sys.stdout)]
logging.basicConfig(level=logging.INFO, handlers=_log_handlers,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Инициализация базы данных
db = Database()

# Игры ядра: Manager создаётся в main()
games_manager: Optional[Manager] = None

# Хранилище игровых состояний пользователей
user_games: Dict[int, Dict] = {}

# Хранилище мультиплеерных игр и данных расстановки
active_games: Dict[int, MultiplayerGame] = {}
placement_data: Dict[int, Any] = {}  # user_id -> ManualPlacementLogic
mp_timers: Dict[int, asyncio.Task] = {}
placement_timers: Dict[int, asyncio.Task] = {}  # таймеры расстановки (3 мин)
game_messages: Dict[int, Dict[str, int]] = {}  # user_id -> {'own': msg_id, 'enemy': msg_id}

TIME_LIMITS = {
    'unlimited': None,
    '10s': 10,
    '30s': 30,
    '1m': 60,
    '5m': 300,
    '1h': 3600
}

PLACEMENT_TIMEOUT = 180  # 3 минуты на расстановку
MAX_TURN_TIMEOUTS = 3  # пропусков хода до технического поражения


async def edit_message_safe(message: types.Message, text: str, reply_markup=None,
                            parse_mode: Optional[str] = None):
    """Безопасно редактировать сообщение (фото или текст)"""
    try:
        if message.photo:
            await message.edit_caption(caption=text, reply_markup=reply_markup,
                                       parse_mode=parse_mode)
        else:
            await message.edit_text(text=text, reply_markup=reply_markup,
                                    parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Error editing message: {e}")


async def send_main_menu(message: types.Message, user: User):
    """Главное меню всех игр (games_core) новым сообщением"""
    player = games_tg.make_player(user.user_id, user.username, user.first_name, user.user_id)
    await games_tg.send_menu(games_manager, bot, player)


async def send_game_field(chat_id: int, language_code: str, player_board: Any):
    """Отправить игровое поле"""
    button_factory = ButtonFactory()
    keyboard_builder = KeyboardBuilder(button_factory)
    kbd = keyboard_builder.create_sea_fight_keyboard(player_board)
    await bot.send_message(
        chat_id=chat_id,
        parse_mode='HTML',
        text=get_translation(language_code, 'text_sea_fight'),
        reply_markup=kbd
    )


async def send_error_message(message: types.Message, user: User):
    """Отправить сообщение об ошибке"""
    button_factory = ButtonFactory()
    keyboard_builder = KeyboardBuilder(button_factory)
    kbd = keyboard_builder.create_sea_menu_keyboard(user.language_code)

    await bot.send_message(
        chat_id=user.user_id,
        parse_mode='HTML',
        text=get_translation(user.language_code, 'error_text_cant_generate_board'),
        reply_markup=kbd
    )


async def blinking_sea_fight(x: int, y: int, board: Any, player_board: Any,
                              chat_id: int, message_id: int, text: str):
    """Анимация потопления корабля"""
    ship = []
    button_factory = ButtonFactory()
    keyboard_builder = KeyboardBuilder(button_factory)

    # Находим все клетки потопленного корабля
    for i in range(ROWS):
        if 0 <= x + i < ROWS:
            if board[x + i][y] == BANG:
                ship.append([x + i, y])
            else:
                break
    for i in range(ROWS):
        if 0 <= x - i < ROWS:
            if board[x - i][y] == BANG:
                ship.append([x - i, y])
            else:
                break
    for i in range(ROWS):
        if 0 <= y + i < ROWS:
            if board[x][y + i] == BANG:
                ship.append([x, y + i])
            else:
                break
    for i in range(ROWS):
        if 0 <= y - i < ROWS:
            if board[x][y - i] == BANG:
                ship.append([x, y - i])
            else:
                break

    # Анимация
    for _ in range(3):
        for e in ship:
            x_coord, y_coord = e
            player_board.update_cell(x_coord, y_coord, BIGBANG)

        new_kbd = keyboard_builder.create_sea_fight_keyboard(player_board)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode='HTML',
            reply_markup=new_kbd
        )

        for e in ship:
            x_coord, y_coord = e
            player_board.update_cell(x_coord, y_coord, BANG)
        await asyncio.sleep(DELAY)

        new_kbd = keyboard_builder.create_sea_fight_keyboard(player_board)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode='HTML',
            reply_markup=new_kbd
        )

        await asyncio.sleep(DELAY)

    # Финальное состояние
    for e in ship:
        x_coord, y_coord = e
        player_board.update_cell(x_coord, y_coord, BIGBANG)


def format_time_remaining(seconds: int) -> str:
    """Форматировать оставшееся время в M:SS"""
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"


async def start_placement_timer(chat_id: int, message_id: int, user_id: int, language_code: str):
    """Запустить таймер расстановки (3 минуты)"""
    start_time = datetime.now()

    while True:
        elapsed = (datetime.now() - start_time).total_seconds()
        remaining = PLACEMENT_TIMEOUT - int(elapsed)

        if remaining <= 0:
            # Время вышло
            cancel_placement(user_id)
            bf = ButtonFactory()
            kb = KeyboardBuilder(bf)
            try:
                menu_kbd = kb.create_sea_menu_keyboard(language_code)
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=get_translation(language_code, 'text_placement_timeout'),
                    reply_markup=menu_kbd
                )
            except Exception as e:
                logger.error(f"Error on placement timeout: {e}")

            # Закрываем игру в БД, иначе она навсегда блокирует новые игры
            try:
                active_game_db = await db.get_active_game_for_user(user_id)
                if active_game_db and active_game_db['status'] in ('waiting', 'placing'):
                    game = MultiplayerGame(**active_game_db)
                    game.status = 'abandoned'
                    game.finished_at = datetime.now()
                    await db.update_multiplayer_game(game)

                    opponent_id = game.get_opponent_id(user_id)
                    for uid in [game.player1_id, game.player2_id]:
                        if uid and uid in active_games:
                            del active_games[uid]
                        if uid and uid != user_id:
                            cancel_placement(uid)

                    # Уведомляем оппонента
                    if opponent_id:
                        opp_user = await db.get_user(opponent_id)
                        opp_lang = opp_user.language_code if opp_user else 'en'
                        try:
                            await bot.send_message(
                                opponent_id,
                                get_translation(opp_lang, 'text_cancelled'),
                                reply_markup=kb.create_sea_menu_keyboard(opp_lang)
                            )
                        except Exception as e:
                            logger.error(f"Error notifying opponent about placement timeout: {e}")
            except Exception as e:
                logger.error(f"Error abandoning game on placement timeout: {e}")

            # Удаляем таймер
            if user_id in placement_timers:
                del placement_timers[user_id]
            return

        # Обновляем текст с таймером каждые ~30 секунд
        # (но не дольше оставшегося времени, чтобы таймаут сработал вовремя)
        await asyncio.sleep(min(30, remaining))

        # Пересчитываем оставшееся время после сна
        elapsed = (datetime.now() - start_time).total_seconds()
        remaining = PLACEMENT_TIMEOUT - int(elapsed)
        if remaining <= 0:
            continue  # таймаут обработает проверка в начале цикла

        # Обновляем сообщение с новым таймером
        placement = placement_data.get(user_id)
        if not placement:
            break

        try:
            timer_text = get_translation(language_code, 'text_placement_timer')
            timer_text = timer_text.replace('%1', format_time_remaining(remaining))
            await _update_placement_message(chat_id, message_id, user_id, language_code, timer_text)
        except Exception as e:
            logger.error(f"Error updating placement timer: {e}")


def cancel_placement(user_id: int):
    """Отменить расстановку для пользователя"""
    if user_id in placement_data:
        del placement_data[user_id]
    if user_id in placement_timers:
        task = placement_timers[user_id]
        if not task.done():
            task.cancel()
        del placement_timers[user_id]


def cancel_turn_timer(game_id: int):
    """Отменить таймер хода"""
    task = mp_timers.pop(game_id, None)
    if task and not task.done():
        task.cancel()


def start_turn_timer(game: MultiplayerGame):
    """(Пере)запустить таймер хода, если у игры задан лимит времени"""
    cancel_turn_timer(game.game_id)
    if not game.time_limit_seconds or game.status != 'active' or not game.current_turn:
        return

    # После рестарта бота ход уже идёт какое-то время — досчитываем остаток,
    # иначе таймер и цифра в шапке доски расходятся
    remaining = turn_seconds_left(game)
    delay = game.time_limit_seconds if remaining is None else max(1, remaining)

    mp_timers[game.game_id] = asyncio.create_task(
        _handle_turn_timeout(game.game_id, game.current_turn, delay)
    )


def turn_timer_interval(delay: int) -> int:
    """Как часто перерисовывать обратный отсчёт при лимите delay секунд.

    Чем длиннее лимит, тем реже обновление: за час игры это ~60 перерисовок,
    а не одна в секунду — Telegram не любит частых правок сообщений.
    """
    return max(5, min(60, delay // 6))


async def _handle_turn_timeout(game_id: int, expected_turn: int, delay: int):
    """Обновлять обратный отсчёт, а по истечении delay — передать ход"""
    deadline = datetime.now() + timedelta(seconds=delay)
    interval = turn_timer_interval(delay)

    while True:
        remaining = (deadline - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        await asyncio.sleep(min(interval, remaining))

        if (deadline - datetime.now()).total_seconds() <= 0:
            break

        # Перерисовываем шапку с новым временем, пока ход всё ещё за тем же игроком
        game = active_games.get(expected_turn)
        if not game or game.game_id != game_id:
            continue
        if game.status != 'active' or game.current_turn != expected_turn:
            continue
        try:
            await update_mp_boards(game)
        except Exception as e:
            logger.error(f"Error refreshing turn timer for game {game_id}: {e}")

    mp_timers.pop(game_id, None)

    game_data = await db.get_multiplayer_game(game_id)
    if not game_data:
        return
    game = MultiplayerGame(**game_data)
    if game.status != 'active' or game.current_turn != expected_turn:
        return

    player_num = game.get_player_number(expected_turn)
    opponent_id = game.get_opponent_id(expected_turn)
    if player_num == 1:
        game.timeouts_count1 += 1
        timeouts = game.timeouts_count1
    else:
        game.timeouts_count2 += 1
        timeouts = game.timeouts_count2

    if opponent_id and timeouts >= MAX_TURN_TIMEOUTS:
        # Слишком много пропусков — техническое поражение
        await finish_mp_game(game, opponent_id,
                             winner_key='text_timeout_victory',
                             loser_key='text_timeout_defeat')
        return

    # Передаём ход оппоненту
    game.current_turn = opponent_id
    game.turn_start_time = datetime.now()
    await db.update_multiplayer_game(game)
    for uid in [game.player1_id, game.player2_id]:
        if uid:
            active_games[uid] = game

    for uid in [game.player1_id, game.player2_id]:
        if not uid:
            continue
        u = await db.get_user(uid)
        lang = u.language_code if u else 'en'
        try:
            await bot.send_message(uid, get_translation(lang, 'text_turn_timeout'))
        except Exception as e:
            logger.error(f"Error notifying turn timeout for {uid}: {e}")

    await update_mp_boards(game)
    start_turn_timer(game)


def display_name(user: Optional[User], fallback_id: int = 0) -> str:
    """То же, но по объекту пользователя"""
    if not user:
        return str(fallback_id)
    return format_player_name(user.username, user.first_name, user.user_id)


MOVE_RESULT_KEYS = {'sunk': 'move_sunk', 'hit': 'move_hit', 'miss': 'move_miss'}


def format_move(attack: Optional[dict], language_code: str, key: str) -> Optional[str]:
    """Строка об одном выстреле ('Вы: 💥 корабль потоплен')"""
    if not attack:
        return None
    result_key = MOVE_RESULT_KEYS.get(attack.get('result'))
    if not result_key:
        return None
    return replace_placeholders(
        get_translation(language_code, key),
        get_translation(language_code, result_key)
    )


def recent_moves(game: MultiplayerGame, uid: int, lang: str) -> list:
    """Два последних хода партии в хронологическом порядке.

    Порядок задаёт номер хода ('seq'), который проставляется при выстреле.
    У партий, начатых до появления номеров, его нет — тогда опираемся на то,
    что ходы чередуются: последним ходил тот, чей сейчас НЕ ход.
    """
    player_num = game.get_player_number(uid)
    enemy_num = 2 if player_num == 1 else 1
    opponent_id = game.get_opponent_id(uid)

    mine = json.loads(game.get_attacks(player_num))
    theirs = json.loads(game.get_attacks(enemy_num))

    entries = []
    if mine:
        moved_last = uid != game.current_turn
        entries.append((mine[-1].get('seq', 1 if moved_last else 0),
                        mine[-1], 'text_your_move'))
    if theirs:
        moved_last = opponent_id is not None and opponent_id != game.current_turn
        entries.append((theirs[-1].get('seq', 1 if moved_last else 0),
                        theirs[-1], 'text_opponent_move'))

    entries.sort(key=lambda e: e[0])
    lines = [format_move(attack, lang, key) for _, attack, key in entries]
    return [line for line in lines if line]


def turn_seconds_left(game: MultiplayerGame) -> Optional[int]:
    """Сколько секунд осталось на текущий ход (None — лимита нет)"""
    if not game.time_limit_seconds or not game.turn_start_time:
        return None
    elapsed = (datetime.now() - game.turn_start_time).total_seconds()
    return max(0, int(game.time_limit_seconds - elapsed))


def build_board_header(game: MultiplayerGame, uid: int, lang: str,
                       profiles: Dict[int, tuple]) -> str:
    """Шапка над досками.

    Порядок хронологический: соперники, затем позапрошлый и прошлый ходы,
    и в самом низу — чей ход сейчас (вместе с таймером).
    """
    lines = []

    opponent_id = game.get_opponent_id(uid)
    if opponent_id:
        opponent_name = profiles.get(opponent_id, (str(opponent_id), 'en'))[0]
        lines.append(replace_placeholders(
            get_translation(lang, 'text_versus'),
            get_translation(lang, 'text_you'),
            opponent_name
        ))

    lines.extend(recent_moves(game, uid, lang))

    is_my_turn = uid == game.current_turn
    turn_text = get_translation(lang, 'text_your_turn' if is_my_turn else 'text_opponent_turn')
    turn_line = f"{'🟢' if is_my_turn else '🔴'} {turn_text}"

    remaining = turn_seconds_left(game)
    if remaining is not None:
        turn_line += " · " + replace_placeholders(
            get_translation(lang, 'text_turn_timer'),
            format_time_remaining(remaining)
        )
    lines.append(turn_line)

    return "\n".join(lines)


async def player_profiles(game: MultiplayerGame) -> Dict[int, tuple]:
    """Имя и язык каждого игрока — один запрос на игрока за перерисовку"""
    profiles = {}
    for uid in (game.player1_id, game.player2_id):
        if uid:
            u = await db.get_user(uid)
            profiles[uid] = (display_name(u, uid), (u.language_code if u else 'en') or 'en')
    return profiles


def render_own_board(own_board: list) -> Board:
    """Отображение своей доски: раненые клетки — 💢, потопленные — 💥.
    В сохранённой доске попадания уже записаны как BANG, промахи — как MISS."""
    display = Board(ROWS, COLS, EMPTY)
    for yy in range(ROWS):
        for xx in range(COLS):
            display.board[yy][xx] = own_board[yy][xx]
    for yy in range(ROWS):
        for xx in range(COLS):
            if own_board[yy][xx] == BANG:
                if not check_ship_sunk_on_board(own_board, xx, yy, ROWS, COLS, SHIP, BANG):
                    display.board[yy][xx] = BIGBANG
    return display


def render_attack_board(attacks: list) -> Board:
    """Отображение доски атаки по истории своих выстрелов"""
    display = Board(ROWS, COLS, EMPTY)
    for atk in attacks:
        ax, ay = atk['x'], atk['y']
        if atk['result'] == 'sunk':
            display.board[ay][ax] = BANG
        elif atk['result'] == 'hit':
            display.board[ay][ax] = BIGBANG
        else:
            display.board[ay][ax] = MISS
    return display


async def finish_mp_game(game: MultiplayerGame, winner_id: int,
                         winner_key: str = 'text_mp_victory',
                         loser_key: str = 'text_mp_defeat'):
    """Завершить мультиплеерную игру: сохранить результат, уведомить игроков, почистить память"""
    loser_id = game.get_opponent_id(winner_id)
    game.status = 'finished'
    game.winner_id = winner_id
    game.finished_at = datetime.now()
    await db.update_multiplayer_game(game)
    cancel_turn_timer(game.game_id)

    game_type = 'mp_full' if game.ship_set == 'full' else 'mp_reduced'

    # Каждый шаг изолирован: сбой статистики или рейтинга не должен
    # оставить игроков без уведомления о результате партии
    if loser_id:
        try:
            await db.update_multiplayer_stats(winner_id, loser_id)
        except Exception as e:
            logger.error(f"Error updating multiplayer stats: {e}")

    ratings = {}
    if loser_id:
        try:
            ratings = await db.apply_match_result(winner_id, loser_id, game_type)
        except Exception as e:
            logger.error(f"Error applying rating for game {game.game_id}: {e}")

    bf = ButtonFactory()
    kb = KeyboardBuilder(bf)

    for uid, key in ((winner_id, winner_key), (loser_id, loser_key)):
        if not uid:
            continue
        u = await db.get_user(uid)
        lang = u.language_code if u else 'en'
        num = game.get_player_number(uid)

        text = replace_placeholders(get_translation(lang, key), game.get_score(num))

        rating = ratings.get(uid)
        if rating:
            delta = rating['delta']
            text += "\n" + replace_placeholders(
                get_translation(lang, 'text_rating_change'),
                rating['rating'],
                f"{delta:+d}"
            )

        try:
            await bot.send_message(uid, text, reply_markup=kb.create_sea_menu_keyboard(lang))
        except Exception as e:
            logger.error(f"Error notifying player {uid} about game end: {e}")

    # Чистим память
    for uid in [game.player1_id, game.player2_id]:
        if uid and uid in active_games:
            del active_games[uid]
        if uid and uid in game_messages:
            del game_messages[uid]


def build_placement_view(placement, language_code: str, timer_suffix: str = None):
    """Собрать текст и клавиатуру интерфейса ручной расстановки"""
    bf = ButtonFactory()
    board = placement.get_board()
    forbidden = placement.get_forbidden_zone()
    current = placement.get_current_ship()

    # Строим клавиатуру доски
    keyboard = []
    for y in range(len(board)):
        row = []
        for x in range(len(board[y])):
            is_current_ship_cell = False
            if current and not current.fixed and (x, y) in current.coordinates:
                is_current_ship_cell = True

            if board[y][x] == SHIP:  # зафиксированный корабль
                cd = f'mplace_fixed_{x}_{y}'
                cell = SHIP
            elif is_current_ship_cell:
                cd = f'mplace_{x}_{y}'
                cell = BUILDING_SHIP
            elif (x, y) in forbidden:
                cd = f'mplace_forbidden_{x}_{y}'
                cell = AVAILABLE
            else:
                cd = f'mplace_{x}_{y}'
                cell = EMPTY
            row.append(InlineKeyboardButton(text=cell, callback_data=cd))
        keyboard.append(row)

    # Кнопки управления
    if current and not current.fixed and current.x != -1:
        keyboard.append([bf.create_button('btn_fix_ship', 'mp_fix_ship', language_code)])
    elif placement.is_complete():
        keyboard.append([bf.create_button('btn_ready', 'mp_ready', language_code)])

    # Кнопка сброса (отдельный ряд) + отмена (отдельный ряд)
    keyboard.append([bf.create_button('btn_reset_placement', 'mp_reset_placement', language_code)])
    keyboard.append([bf.create_button('btn_cancel', 'mp_cancel', language_code)])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    text = f"{get_translation(language_code, 'text_manual_placement')}\n\n{placement.get_ships_summary()}"

    # Добавляем таймер в последнюю строку
    if timer_suffix:
        text += f"\n{timer_suffix}"

    return text, markup


def placement_timer_text(language_code: str, seconds: int) -> str:
    """Строка таймера расстановки"""
    timer_text = get_translation(language_code, 'text_placement_timer')
    return timer_text.replace('%1', format_time_remaining(seconds))


async def _update_placement_message(chat_id: int, message_id: int, user_id: int,
                                     language_code: str, timer_suffix: str = None):
    """Обновить сообщение расстановки"""
    placement = placement_data.get(user_id)
    if not placement:
        return

    text, markup = build_placement_view(placement, language_code, timer_suffix)

    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=text,
            parse_mode='HTML',
            reply_markup=markup
        )
    except Exception:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode='HTML',
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error updating placement message: {e}")


async def send_mp_manual_placement(message_or_callback_msg: types.Message, language_code: str, user_id: int):
    """Отправить интерфейс ручной расстановки кораблей для мультиплеера"""
    placement = placement_data.get(user_id)
    if not placement:
        return

    timer_text = placement_timer_text(language_code, PLACEMENT_TIMEOUT)
    text, markup = build_placement_view(placement, language_code, timer_text)

    message_id = message_or_callback_msg.message_id
    try:
        await edit_message_safe(message_or_callback_msg, text, reply_markup=markup)
    except Exception:
        try:
            msg = await message_or_callback_msg.answer(text, reply_markup=markup)
            message_id = msg.message_id
        except Exception as e:
            logger.error(f"Error sending placement: {e}")
            return

    # Запускаем таймер расстановки
    if user_id in placement_timers:
        placement_timers[user_id].cancel()

    chat_id = message_or_callback_msg.chat.id if hasattr(message_or_callback_msg, 'chat') else user_id
    placement_timers[user_id] = asyncio.create_task(
        start_placement_timer(chat_id, message_id, user_id, language_code)
    )


async def _send_new_placement_message(chat_id: int, language_code: str, placement):
    """Отправить новое сообщение с полем расстановки и запустить таймер"""
    timer_text = placement_timer_text(language_code, PLACEMENT_TIMEOUT)
    text, markup = build_placement_view(placement, language_code, timer_text)

    msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='HTML',
        reply_markup=markup
    )

    # Запускаем таймер
    if chat_id in placement_timers:
        placement_timers[chat_id].cancel()
    placement_timers[chat_id] = asyncio.create_task(
        start_placement_timer(chat_id, msg.message_id, chat_id, language_code)
    )


# ==================== HANDLERS ====================


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Обработчик команды /start и глубоких ссылок для мультиплеера"""
    try:
        logger.info(f"Received /start command from user {message.from_user.id}")
        user = message.from_user
        user_id = user.id
        logger.info(f"Processing user: {user_id}, lang: {user.language_code}")

        # Сохраняем информацию о пользователе
        args = message.text.split()
        source = args[1] if len(args) > 1 else None

        db_user = User(
            user_id=user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            language_code=user.language_code or 'en',
            is_bot=user.is_bot,
            is_premium=user.is_premium,
            source=source
        )
        logger.info(f"Saving user to database...")
        await db.save_user(db_user)
        logger.info(f"User saved successfully")

        # Если пришёл по ссылке приглашения в мультиплеер
        if source and source.startswith('mp_'):
            try:
                join_code = source[3:]  # код подключения (6 символов)
                # Ищем игру по коду
                game_data = await db.get_game_by_join_code(join_code)
                if game_data:
                    game_id = game_data['game_id']
                    await handle_multiplayer_join(message, db_user, game_id, state)
                    return
                else:
                    await message.answer(get_translation(db_user.language_code, 'text_game_not_found'))
                    return
            except Exception as e:
                logger.warning(f"Invalid multiplayer link: {source}, error: {e}")
                await message.answer(get_translation(db_user.language_code, 'text_game_not_found'))
                return

        # Иначе — обычное начало: главное меню
        logger.info(f"Sending main menu to user {user_id}...")
        await send_main_menu(message, db_user)
        logger.info(f"Main menu sent successfully")
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}", exc_info=True)
        try:
            await message.answer(f"Ошибка: {e}")
        except:
            pass


@dp.callback_query(F.data == 'sea_menu')
async def handle_sea_menu(callback: types.CallbackQuery, state: FSMContext):
    """Меню морского боя (из главного меню игр)"""
    language_code = callback.from_user.language_code or 'en'
    kb = KeyboardBuilder(ButtonFactory())
    await edit_message_safe(
        callback.message,
        get_translation(language_code, 'text_start_msg'),
        reply_markup=kb.create_sea_menu_keyboard(language_code)
    )
    await callback.answer()


@dp.callback_query(F.data == 'newgame')
async def handle_new_game(callback: types.CallbackQuery, state: FSMContext):
    """Начать новую игру — предлагаем выбрать набор кораблей"""
    logger.info(f"Received callback: {callback.data} from user {callback.from_user.id}")
    user = callback.from_user
    user_id = user.id
    language_code = user.language_code or 'en'

    # Переключаем в состояние выбора набора кораблей
    await state.set_state(SinglePlayerStates.choosing_ship_set)

    bf = ButtonFactory()
    kb = KeyboardBuilder(bf)
    markup = kb.create_ship_set_keyboard(language_code)

    await edit_message_safe(
        callback.message,
        get_translation(language_code, 'text_choose_ship_set'),
        reply_markup=markup
    )
    await callback.answer()


@dp.callback_query(F.data.startswith('shipset_'), SinglePlayerStates.choosing_ship_set)
async def handle_single_ship_set(callback: types.CallbackQuery, state: FSMContext):
    """Обработать выбор набора кораблей для одиночной игры"""
    user = callback.from_user
    user_id = user.id
    language_code = user.language_code or 'en'

    ship_set = callback.data.replace('shipset_', '')  # 'full' or 'reduced'
    ships = SHIPS if ship_set == 'full' else SHIPS_REDUCED

    await state.update_data(ship_set=ship_set)

    # Получаем информацию о пользователе
    db_user = await db.get_user(user_id)
    if not db_user:
        db_user = User(
            user_id=user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            language_code=language_code
        )

    # Генерируем новую игру
    game_logic = GameLogic(ROWS, COLS, EMPTY, SHIP)
    if game_logic.generate_board(ships):
        user_games[user_id] = {
            'board': game_logic.board.board,
            'player_board': game_logic.player_board.board,
            'score': 0,
            'operation': '',
            'ship_set': ship_set,
        }

        # Отправляем только игровое поле (без картинки)
        await send_game_field(user_id, db_user.language_code, game_logic.player_board)
    else:
        await send_error_message(callback.message, db_user)

    await state.clear()
    await callback.answer()


# ==================== MULTIPLAYER ====================


@dp.callback_query(F.data == 'multiplayer_start')
async def handle_multiplayer_start(callback: types.CallbackQuery, state: FSMContext):
    """Начать мультиплеер — выбор времени на ход"""
    user = callback.from_user
    user_id = user.id
    language_code = user.language_code or 'en'

    logger.info(f"Multiplayer start requested by user {user_id}")

    try:
        # Проверяем, нет ли активной игры
        active_game = await db.get_active_game_for_user(user_id)
        if active_game:
            # Есть активная игра — предлагаем сбросить или вернуться
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=get_translation(language_code, 'btn_return_game'),
                    callback_data='mp_return'
                )
            ], [
                InlineKeyboardButton(
                    text=get_translation(language_code, 'btn_give_up'),
                    callback_data='mp_surrender'
                )
            ]])
            await edit_message_safe(
                callback.message,
                get_translation(language_code, 'error_active_game'),
                reply_markup=markup
            )
            await callback.answer()
            return

        # Переключаем в состояние выбора времени
        await state.set_state(MultiplayerStates.choosing_time_limit)

        bf = ButtonFactory()
        keyboard = [
            [bf.create_button('time_unlimited', 'time_unlimited', language_code)],
            [bf.create_button('time_10s', 'time_10s', language_code),
             bf.create_button('time_30s', 'time_30s', language_code)],
            [bf.create_button('time_1m', 'time_1m', language_code),
             bf.create_button('time_5m', 'time_5m', language_code)],
            [bf.create_button('time_1h', 'time_1h', language_code)],
            [bf.create_button('btn_cancel', 'mp_cancel', language_code)],
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        await edit_message_safe(
            callback.message,
            get_translation(language_code, 'text_choose_time_limit'),
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Error in handle_multiplayer_start: {e}", exc_info=True)
        await callback.answer(get_translation(language_code, 'error_creating_game'), show_alert=True)


@dp.callback_query(F.data == 'mp_cancel')
async def handle_mp_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Отмена мультиплеера — возврат в главное меню"""
    user_id = callback.from_user.id
    language_code = callback.from_user.language_code or 'en'

    # Удаляем игру если была создана
    state_data = await state.get_data()
    game_id = state_data.get('game_id')
    if game_id:
        game_data = await db.get_multiplayer_game(game_id)
        if game_data:
            game_data['status'] = 'abandoned'
            game_data['finished_at'] = datetime.now()
            game = MultiplayerGame(**game_data)
            await db.update_multiplayer_game(game)
            cancel_turn_timer(game_id)
            for uid in [game.player1_id, game.player2_id]:
                if uid and uid in active_games:
                    del active_games[uid]

    # Чистим расстановку
    cancel_placement(user_id)

    await state.clear()

    # Возврат в главное меню
    db_user = await db.get_user(user_id)
    if not db_user:
        db_user = User(
            user_id=user_id,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            username=callback.from_user.username,
            language_code=language_code
        )
    await send_main_menu(callback.message, db_user)
    await callback.answer()


@dp.callback_query(F.data.startswith('time_'), MultiplayerStates.choosing_time_limit)
async def handle_time_limit(callback: types.CallbackQuery, state: FSMContext):
    """Обработать выбор времени на ход — переходим к выбору набора кораблей"""
    user = callback.from_user
    user_id = user.id
    language_code = user.language_code or 'en'

    # Сохраняем выбор времени
    time_key = callback.data.replace('time_', '')  # e.g. 'unlimited', '10s', '1m'
    time_limit = TIME_LIMITS.get(time_key)

    await state.update_data(time_limit=time_limit)
    await state.set_state(MultiplayerStates.choosing_ship_set)

    bf = ButtonFactory()
    kb = KeyboardBuilder(bf)
    markup = kb.create_ship_set_keyboard(language_code)

    await edit_message_safe(
        callback.message,
        get_translation(language_code, 'text_choose_ship_set'),
        reply_markup=markup
    )
    await callback.answer()


@dp.callback_query(F.data.startswith('shipset_'), MultiplayerStates.choosing_ship_set)
async def handle_mp_ship_set(callback: types.CallbackQuery, state: FSMContext):
    """Обработать выбор набора кораблей для мультиплеера"""
    user = callback.from_user
    user_id = user.id
    language_code = user.language_code or 'en'

    ship_set = callback.data.replace('shipset_', '')  # 'full' or 'reduced'
    await state.update_data(ship_set=ship_set)
    await state.set_state(MultiplayerStates.choosing_placement_mode)

    bf = ButtonFactory()
    keyboard = [
        [bf.create_button('placement_auto', 'placement_auto', language_code)],
        [bf.create_button('placement_manual', 'placement_manual', language_code)],
        [bf.create_button('btn_cancel', 'mp_cancel', language_code)],
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await edit_message_safe(
        callback.message,
        get_translation(language_code, 'text_choose_placement_mode'),
        reply_markup=markup
    )
    await callback.answer()


@dp.callback_query(F.data.in_(['placement_auto', 'placement_manual']))
async def handle_placement_mode(callback: types.CallbackQuery, state: FSMContext):
    """Обработать выбор режима расстановки и создать игру"""
    user = callback.from_user
    user_id = user.id
    language_code = user.language_code or 'en'

    placement_mode = callback.data.replace('placement_', '')  # 'auto' or 'manual'
    state_data = await state.get_data()
    time_limit = state_data.get('time_limit')
    ship_set = state_data.get('ship_set', 'full')

    try:
        # Создаём игру в БД (join_code генерируется внутри)
        game_id = await db.create_multiplayer_game(
            player1_id=user_id,
            placement_mode=placement_mode,
            time_limit=time_limit,
            ship_set=ship_set
        )

        game_data = await db.get_multiplayer_game(game_id)
        game = MultiplayerGame(**game_data)

        # Сохраняем в памяти
        active_games[user_id] = game
        await state.update_data(game_id=game_id)

        await state.set_state(MultiplayerStates.waiting_for_opponent)

        # Первое сообщение: предложение переслать ссылку
        invite_text = get_translation(language_code, 'text_invite_friend')
        cancel_kbd = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=get_translation(language_code, 'btn_cancel'),
                callback_data='cancel_game'
            )
        ]])
        await edit_message_safe(callback.message, invite_text, reply_markup=cancel_kbd)

        # Второе сообщение: ссылка и параметры игры
        bot_username = (await bot.get_me()).username
        link = f"https://t.me/{bot_username}?start=mp_{game.join_code}"

        # Описание параметров игры
        mode_text = get_translation(language_code, 'placement_auto' if placement_mode == 'auto' else 'placement_manual')
        time_text = get_translation(language_code, 'time_unlimited') if time_limit is None else \
            f"{time_limit}s" if time_limit < 60 else f"{time_limit // 60}m"
        ship_set_text = get_translation(language_code, 'ship_set_full' if ship_set == 'full' else 'ship_set_reduced')

        params_text = get_translation(language_code, 'text_game_params')
        params_text = replace_placeholders(params_text, link, mode_text, time_text, ship_set_text)

        await callback.message.answer(params_text)

        # Для ручной расстановки — доп. подсказка
        if placement_mode == 'manual':
            await callback.message.answer(
                get_translation(language_code, 'text_manual_placement_after_join')
            )

        await callback.answer()

    except Exception as e:
        logger.error(f"Error creating multiplayer game: {e}", exc_info=True)
        await callback.answer(get_translation(language_code, 'error_creating_game'), show_alert=True)


@dp.callback_query(F.data == 'mp_reset_placement')
async def handle_reset_placement(callback: types.CallbackQuery, state: FSMContext):
    """Сбросить расстановку и начать сначала"""
    user_id = callback.from_user.id
    language_code = callback.from_user.language_code or 'en'

    placement = placement_data.get(user_id)
    if not placement:
        await callback.answer()
        return

    placement.reset_all()
    await send_mp_manual_placement(callback.message, language_code, user_id)
    await callback.answer()


async def handle_multiplayer_join(message: types.Message, db_user: User, game_id: int,
                                   state: Optional[FSMContext] = None):
    """Присоединиться к мультиплеерной игре по ссылке"""
    user_id = db_user.user_id
    language_code = db_user.language_code or 'en'

    # 1. Получаем игру по коду
    game_data = await db.get_multiplayer_game(game_id)
    if not game_data:
        await message.answer(get_translation(language_code, 'text_game_not_found'))
        return

    game = MultiplayerGame(**game_data)

    # 2. Если пользователь — владелец этой игры, показываем подсказку
    if game.player1_id == user_id:
        await message.answer(get_translation(language_code, 'text_own_game_hint'))
        return

    # 3. Проверяем, нет ли другой активной игры
    active_game = await db.get_active_game_for_user(user_id)
    if active_game:
        await message.answer(get_translation(language_code, 'error_active_game'))
        return

    # 4. Остальные стандартные проверки
    if game.status != 'waiting':
        await message.answer(get_translation(language_code, 'text_game_not_found'))
        return

    if game.player2_id is not None:
        await message.answer(get_translation(language_code, 'text_game_full'))
        return

    # Присоединяемся
    joined = await db.join_multiplayer_game(game_id, user_id)
    if not joined:
        await message.answer(get_translation(language_code, 'text_game_full'))
        return

    # Обновляем в памяти
    game.player2_id = user_id
    game.status = 'placing'
    active_games[user_id] = game
    # Обновляем и у первого игрока
    active_games[game.player1_id] = game

    # Сохраняем game_id в состоянии второго игрока (нужно для mp_ready)
    if state:
        await state.update_data(game_id=game_id)

    # Определяем набор кораблей
    ship_set = getattr(game, 'ship_set', None)
    if ship_set is None:
        # Пробуем достать из БД-данных (старый формат)
        ship_set = game_data.get('ship_set', 'full') if isinstance(game_data, dict) else 'full'
    ships = SHIPS if ship_set == 'full' else SHIPS_REDUCED

    # Имена обеих сторон: кто приглашал (host) и кто подключился (joiner)
    host_user = await db.get_user(game.player1_id)
    host_name = display_name(host_user, game.player1_id)
    joiner_name = display_name(db_user, user_id)

    # Уведомляем первого игрока и начинаем расстановку
    try:
        p1_lang = host_user.language_code if host_user else 'en'

        if game.placement_mode == 'manual':
            # Ручная расстановка для первого игрока
            p1_placement = ManualPlacementLogic(ROWS, COLS, ship_sizes=ships)
            placement_data[game.player1_id] = p1_placement

            await bot.send_message(
                chat_id=game.player1_id,
                text=replace_placeholders(
                    get_translation(p1_lang, 'text_opponent_joined_placement'),
                    html.escape(joiner_name)),
                parse_mode='HTML'
            )
            # Отправляем поле для расстановки
            await _send_new_placement_message(game.player1_id, p1_lang, p1_placement)
        else:
            await bot.send_message(
                chat_id=game.player1_id,
                text=replace_placeholders(
                    get_translation(p1_lang, 'text_opponent_joined'),
                    joiner_name)
            )
    except Exception as e:
        logger.error(f"Error notifying player 1: {e}")

    # Второму игроку — начинаем расстановку
    if game.placement_mode == 'manual':
        p2_placement = ManualPlacementLogic(ROWS, COLS, ship_sizes=ships)
        placement_data[user_id] = p2_placement

        await message.answer(
            replace_placeholders(
                get_translation(language_code, 'text_you_joined_placement'),
                html.escape(host_name)),
            parse_mode='HTML'
        )
        await _send_new_placement_message(user_id, language_code, p2_placement)
    else:
        # Автоматическая расстановка - генерируем доски и начинаем игру
        await message.answer(replace_placeholders(
            get_translation(language_code, 'text_you_joined'), host_name))
        
        # Генерируем доски для обоих игроков
        # Доска для первого игрока
        game1 = GameLogic(ROWS, COLS, EMPTY, SHIP)
        game1.generate_board(ships)
        board1 = game1.board.board
        
        # Доска для второго игрока
        game2 = GameLogic(ROWS, COLS, EMPTY, SHIP)
        game2.generate_board(ships)
        board2 = game2.board.board
        
        # Сохраняем доски и флаги готовности (статус активирует start_mp_game)
        game.board1 = json.dumps(board1)
        game.board2 = json.dumps(board2)
        game.placement_complete1 = True
        game.placement_complete2 = True
        await db.update_multiplayer_game(game)

        # Начинаем игру для обоих игроков
        await start_mp_game(message, game_id, user_id)


@dp.callback_query(F.data == 'mp_return')
async def handle_mp_return(callback: types.CallbackQuery, state: FSMContext):
    """Вернуться к активной игре — переслать игровые поля"""
    user_id = callback.from_user.id
    language_code = callback.from_user.language_code or 'en'

    active_game = await db.get_active_game_for_user(user_id)
    if not active_game:
        # Игры уже нет — в главное меню
        db_user = await db.get_user(user_id)
        if not db_user:
            db_user = User(user_id=user_id, first_name=callback.from_user.first_name,
                           language_code=language_code)
        await send_main_menu(callback.message, db_user)
        await callback.answer()
        return

    game = MultiplayerGame(**active_game)
    active_games[user_id] = game
    if game.player1_id:
        active_games[game.player1_id] = game
    if game.player2_id:
        active_games[game.player2_id] = game

    if game.status == 'waiting':
        # Ещё ждём второго игрока
        bot_username = (await bot.get_me()).username
        link = f"https://t.me/{bot_username}?start=mp_{game.join_code}"
        text = get_translation(language_code, 'text_invite_friend') + f"\n\n{link}"
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=get_translation(language_code, 'btn_give_up'),
                callback_data='mp_surrender'
            )
        ]])
        await edit_message_safe(callback.message, text, reply_markup=markup)
        await callback.answer()
        return

    if game.status == 'active':
        # Активная игра — пересылаем доски
        await start_mp_game(callback.message, game.game_id, user_id, resume=True)
        await callback.answer()
        return

    # Другой статус — в главное меню
    db_user = await db.get_user(user_id)
    if not db_user:
        db_user = User(user_id=user_id, first_name=callback.from_user.first_name,
                       language_code=language_code)
    await send_main_menu(callback.message, db_user)
    await callback.answer()


@dp.callback_query(F.data == 'mp_surrender')
async def handle_mp_surrender(callback: types.CallbackQuery, state: FSMContext):
    """Сбросить активную игру и вернуться в главное меню"""
    user_id = callback.from_user.id
    language_code = callback.from_user.language_code or 'en'

    # Ищем активную игру в БД и помечаем abandoned
    active_game = await db.get_active_game_for_user(user_id)
    if active_game:
        game = MultiplayerGame(**active_game)
        game.status = 'abandoned'
        game.finished_at = datetime.now()
        await db.update_multiplayer_game(game)
        cancel_turn_timer(game.game_id)

        # Уведомляем оппонента если есть
        opponent_id = game.get_opponent_id(user_id)
        if opponent_id:
            opp_user = await db.get_user(opponent_id)
            opp_lang = opp_user.language_code if opp_user else 'en'
            try:
                bf = ButtonFactory()
                kb = KeyboardBuilder(bf)
                menu_kbd = kb.create_sea_menu_keyboard(opp_lang)
                await bot.send_message(
                    opponent_id,
                    get_translation(opp_lang, 'text_cancelled'),
                    reply_markup=menu_kbd
                )
            except Exception as e:
                logger.error(f"Error notifying opponent: {e}")

        # Чистим из памяти
        for uid in [game.player1_id, game.player2_id]:
            if uid and uid in active_games:
                del active_games[uid]
            cancel_placement(uid)
            if uid and uid in game_messages:
                del game_messages[uid]

    await state.clear()

    # Возврат в главное меню
    db_user = await db.get_user(user_id)
    if not db_user:
        db_user = User(
            user_id=user_id,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            username=callback.from_user.username,
            language_code=language_code
        )
    await send_main_menu(callback.message, db_user)
    await callback.answer()


@dp.callback_query(F.data == 'cancel_game')
async def handle_cancel_game(callback: types.CallbackQuery, state: FSMContext):
    """Отменить ожидание/игру"""
    user_id = callback.from_user.id
    language_code = callback.from_user.language_code or 'en'

    state_data = await state.get_data()
    game_id = state_data.get('game_id')

    if game_id:
        game_data = await db.get_multiplayer_game(game_id)
        if game_data:
            game_data['status'] = 'abandoned'
            game_data['finished_at'] = datetime.now()
            game = MultiplayerGame(**game_data)
            await db.update_multiplayer_game(game)
            cancel_turn_timer(game_id)

            # Удаляем из памяти
            for uid in [game.player1_id, game.player2_id]:
                if uid and uid in active_games:
                    del active_games[uid]

    cancel_placement(user_id)
    await state.clear()
    await edit_message_safe(callback.message, get_translation(language_code, 'text_cancelled'))
    await callback.answer()


@dp.callback_query(F.data == 'mp_fix_ship')
async def handle_mp_fix_ship(callback: types.CallbackQuery, state: FSMContext):
    """Зафиксировать текущий корабль и перейти к следующему"""
    user_id = callback.from_user.id
    language_code = callback.from_user.language_code or 'en'

    placement = placement_data.get(user_id)
    if not placement:
        await callback.answer(get_translation(language_code, 'error_generic'))
        return

    current = placement.get_current_ship()
    if not current or not current.is_valid():
        await callback.answer(get_translation(language_code, 'error_invalid_move'))
        return

    # Фиксируем и переходим к следующему
    placement.fix_current_ship()
    placement.next_ship()

    await send_mp_manual_placement(callback.message, language_code, user_id)
    await callback.answer()


@dp.callback_query(F.data.startswith('mplace_'))
async def handle_mp_placement_click(callback: types.CallbackQuery, state: FSMContext):
    """Обработка кликов при расстановке кораблей в мультиплеере"""
    user_id = callback.from_user.id
    language_code = callback.from_user.language_code or 'en'
    data = callback.data

    placement = placement_data.get(user_id)
    if not placement:
        await callback.answer(get_translation(language_code, 'error_placement_not_found'))
        return

    # Запрещённые и уже занятые клетки — игнорируем
    if data.startswith('mplace_forbidden_') or data.startswith('mplace_fixed_'):
        await callback.answer()
        return

    parts = data.split('_')
    if len(parts) != 3:
        await callback.answer()
        return

    x, y = int(parts[1]), int(parts[2])
    current = placement.get_current_ship()

    # Если корабль уже стоит на этой же клетке — поворачиваем
    if current and not current.fixed and current.x == x and current.y == y:
        rotated, error_key = placement.rotate_current_ship()
        if rotated:
            await _update_placement_message(
                callback.message.chat.id, callback.message.message_id,
                user_id, language_code
            )
            await callback.answer()
            return
        else:
            error_msg = get_translation(language_code, error_key)
            await callback.answer(error_msg, show_alert=False)
            return

    # Иначе — ставим корабль в новую клетку
    success, error_key = placement.place_ship_center(x, y)
    if success:
        await _update_placement_message(
            callback.message.chat.id, callback.message.message_id,
            user_id, language_code
        )
    else:
        # Показываем конкретную причину ошибки как всплывающее уведомление
        error_msg = get_translation(language_code, error_key)
        await callback.answer(error_msg, show_alert=False)
        return

    await callback.answer()


@dp.callback_query(F.data == 'mp_ready')
async def handle_mp_ready(callback: types.CallbackQuery, state: FSMContext):
    """Готов к игре после расстановки"""
    user_id = callback.from_user.id
    language_code = callback.from_user.language_code or 'en'

    placement = placement_data.get(user_id)
    if not placement or not placement.is_complete():
        await callback.answer(get_translation(language_code, 'error_invalid_move'))
        return

    # Сначала сохраняем доску из расстановки в игру
    placement = placement_data.get(user_id)
    if placement:
        board_data = placement.get_board()  # list of lists with SHIP/EMPTY symbols
        # Убираем запрещённые зоны (🟩) — они не часть доски
        for y in range(len(board_data)):
            for x in range(len(board_data[y])):
                if board_data[y][x] not in (SHIP, EMPTY):
                    board_data[y][x] = EMPTY
    else:
        board_data = None

    # Отменяем таймер расстановки (НЕ трогаем placement_data пока)
    if user_id in placement_timers:
        task = placement_timers[user_id]
        if not task.done():
            task.cancel()
        del placement_timers[user_id]

    state_data = await state.get_data()
    game_id = state_data.get('game_id')
    if not game_id:
        # FSM-состояние могло потеряться (рестарт бота) — ищем игру в БД
        active_game_db = await db.get_active_game_for_user(user_id)
        if active_game_db:
            game_id = active_game_db['game_id']
            await state.update_data(game_id=game_id)
    if not game_id:
        # Теперь чистим placement
        if user_id in placement_data:
            del placement_data[user_id]
        await callback.answer(get_translation(language_code, 'error_no_game'))
        return

    # Получаем игру из БД для определения номера игрока
    game_data = await db.get_multiplayer_game(game_id)
    game = MultiplayerGame(**game_data)

    player_num = game.get_player_number(user_id)

    # Сохраняем доску точечно, чтобы не затереть флаги готовности оппонента
    if board_data:
        await db.update_board(game_id, player_num, json.dumps(board_data))

    # Теперь чистим placement_data
    if user_id in placement_data:
        del placement_data[user_id]

    # Обновляем статус в БД
    await db.set_placement_complete(game_id, player_num)

    # Перезагружаем данные из БД, чтобы получить актуальное состояние
    game_data = await db.get_multiplayer_game(game_id)
    game = MultiplayerGame(**game_data)

    # Обновляем в памяти
    active_games[user_id] = game
    if game.player1_id:
        active_games[game.player1_id] = game
    if game.player2_id:
        active_games[game.player2_id] = game

    # Проверяем — оба готовы?
    if game.placement_complete1 and game.placement_complete2:
        # Оба готовы — начинаем!
        await start_mp_game(callback.message, game_id, user_id)
    else:
        # Ждём второго
        await edit_message_safe(
            callback.message,
            get_translation(language_code, 'text_waiting_ready')
        )

    await callback.answer()


async def start_mp_game(message: types.Message, game_id: int, user_id: int,
                        resume: bool = False):
    """Начать фазу игры мультиплеера (resume=True — переслать доски уже активной игры)"""
    game_data = await db.get_multiplayer_game(game_id)
    if not game_data:
        return

    game = MultiplayerGame(**game_data)

    if not resume:
        # Атомарная активация: при одновременном «Готов» доски разошлёт только один вызов
        activated = await db.try_activate_game(game_id, game.player1_id)
        if not activated:
            return
        game_data = await db.get_multiplayer_game(game_id)
        game = MultiplayerGame(**game_data)

    if game.status != 'active':
        return

    # Обновляем в памяти
    active_games[game.player1_id] = game
    active_games[game.player2_id] = game

    # Отправляем обоим игрокам
    profiles = await player_profiles(game)

    for uid in [game.player1_id, game.player2_id]:
        lang = profiles.get(uid, ('', 'en'))[1]
        player_num = game.get_player_number(uid)

        # Своя доска (попадания и промахи уже записаны в неё)
        own_board = json.loads(game.get_board(player_num))
        display_board = render_own_board(own_board)

        bf = ButtonFactory()
        kb = KeyboardBuilder(bf)
        own_kbd = kb.create_sea_fight_keyboard(display_board, callback_prefix='mpown')

        header = build_board_header(game, uid, lang, profiles)
        own_label = get_translation(lang, 'text_own_ships_field')

        own_msg = await bot.send_message(
            chat_id=uid,
            text=f"{header}\n\n{own_label}",
            reply_markup=own_kbd
        )

        # Доска для атаки (противник)
        my_attacks = json.loads(game.get_attacks(player_num))
        attack_board = render_attack_board(my_attacks)

        attack_kbd = kb.create_sea_fight_keyboard(attack_board, callback_prefix='mpfire')

        attack_label = get_translation(lang, 'text_attack_field')

        attack_msg = await bot.send_message(
            chat_id=uid,
            text=f"{header}\n\n{attack_label}",
            reply_markup=attack_kbd
        )

        game_messages[uid] = {'own': own_msg.message_id, 'enemy': attack_msg.message_id}

    # Запускаем таймер хода (если игра с лимитом времени)
    start_turn_timer(game)


@dp.callback_query(F.data.startswith('mpown_'))
async def handle_mp_own_click(callback: types.CallbackQuery, state: FSMContext):
    """Клик по полю своих кораблей — предупреждение"""
    language_code = callback.from_user.language_code or 'en'
    await callback.answer(get_translation(language_code, 'text_own_field_warning'), show_alert=True)


@dp.callback_query(F.data.startswith('mpfire_'))
async def handle_mp_fire(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выстрела в мультиплеере"""
    user_id = callback.from_user.id
    language_code = callback.from_user.language_code or 'en'

    game = active_games.get(user_id)
    if not game or game.status != 'active':
        # Фоллбэк: пробуем восстановить игру из БД
        active_game_db = await db.get_active_game_for_user(user_id)
        if active_game_db:
            game = MultiplayerGame(**active_game_db)
            if game.status == 'active':
                # Восстанавливаем в память для обоих игроков
                active_games[user_id] = game
                opponent_id = game.get_opponent_id(user_id)
                if opponent_id and opponent_id not in active_games:
                    active_games[opponent_id] = game
                # После рестарта бота сообщения с досками потеряны — пересылаем заново
                if user_id not in game_messages or (opponent_id and opponent_id not in game_messages):
                    await start_mp_game(callback.message, game.game_id, user_id, resume=True)
            else:
                await callback.answer(get_translation(language_code, 'error_game_not_active'))
                return
        else:
            await callback.answer(get_translation(language_code, 'error_no_active_game'))
            return

    if game.current_turn != user_id:
        await callback.answer(get_translation(language_code, 'error_not_your_turn'), show_alert=True)
        return

    _, x_str, y_str = callback.data.split('_')
    x, y = int(x_str), int(y_str)

    player_num = game.get_player_number(user_id)
    enemy_num = 2 if player_num == 1 else 1
    enemy_board = json.loads(game.get_board(enemy_num))
    my_attacks = json.loads(game.get_attacks(player_num))

    # Проверяем — не стрелял ли уже сюда
    for atk in my_attacks:
        if atk['x'] == x and atk['y'] == y:
            await callback.answer(get_translation(language_code, 'error_invalid_move'))
            return

    # Проверяем попадание
    ship_cells = set()
    if enemy_board[y][x] == SHIP:
        # Помечаем попадание как BANG
        enemy_board[y][x] = BANG
        sunk = check_ship_sunk_on_board(enemy_board, x, y, ROWS, COLS, SHIP, BANG)

        if sunk:
            result = 'sunk'
            game.update_score(player_num, 20)
            # Помечаем все клетки потопленного корабля в истории атак,
            # чтобы на доске атаки весь корабль показывался как 💥
            ship_cells = collect_ship_cells(enemy_board, x, y, ROWS, COLS, (BANG,))
            for atk in my_attacks:
                if (atk['x'], atk['y']) in ship_cells:
                    atk['result'] = 'sunk'
        else:
            result = 'hit'
            # Ранен но не убит — тоже BANG в доске, а 💢 только при отображении
            game.update_score(player_num, 10)
    else:
        result = 'miss'
        enemy_board[y][x] = MISS

    # Сохраняем атаку. seq — сквозной номер хода в партии: по нему шапка доски
    # выстраивает ходы обоих игроков в хронологическом порядке
    enemy_attacks = json.loads(game.get_attacks(enemy_num))
    my_attacks.append({'x': x, 'y': y, 'result': result,
                       'seq': len(my_attacks) + len(enemy_attacks)})

    # Обновляем игру
    if player_num == 1:
        game.attacks1 = json.dumps(my_attacks)
        game.board2 = json.dumps(enemy_board)
    else:
        game.attacks2 = json.dumps(my_attacks)
        game.board1 = json.dumps(enemy_board)

    # Переключаем ход. turn_start_time нужен, чтобы таймер в шапке доски
    # показывал время, оставшееся именно на текущий ход
    game.current_turn = game.get_opponent_id(user_id)
    game.last_move_time = datetime.now()
    game.turn_start_time = datetime.now()

    await db.update_multiplayer_game(game)
    active_games[game.player1_id] = game
    active_games[game.player2_id] = game

    # Проверяем победу
    all_sunk = True
    for row in enemy_board:
        for cell in row:
            if cell == SHIP:
                all_sunk = False
                break
        if not all_sunk:
            break

    if all_sunk:
        # Последний корабль: доигрываем анимацию и только затем объявляем итог.
        # Фоновой задачей, чтобы не задерживать ответ на нажатие
        cancel_turn_timer(game.game_id)
        await update_mp_boards(game)
        asyncio.create_task(_animate_then_finish(game, ship_cells, player_num, user_id))
        await callback.answer(get_translation(language_code, 'text_killed'))
        return

    await update_mp_boards(game)
    start_turn_timer(game)

    if result == 'sunk':
        # Анимация фоном — ходы при этом не блокируются
        asyncio.create_task(animate_mp_sunk(game, ship_cells, player_num))
        await callback.answer(get_translation(language_code, 'text_killed'))
    elif result == 'hit':
        await callback.answer(get_translation(language_code, 'text_damaged'))
    else:
        await callback.answer(get_translation(language_code, 'text_miss'))


async def _animate_then_finish(game: MultiplayerGame, ship_cells: set,
                               attacker_num: int, winner_id: int):
    """Проиграть анимацию последнего потопления и завершить игру"""
    try:
        await animate_mp_sunk(game, ship_cells, attacker_num)
    except Exception as e:
        logger.error(f"Error animating final ship in game {game.game_id}: {e}")
    finally:
        await finish_mp_game(game, winner_id)


async def update_mp_boards(game: MultiplayerGame, highlight: Optional[tuple] = None,
                           profiles: Optional[Dict[int, tuple]] = None):
    """Обновить доски обоих игроков.

    highlight — (клетки, символ) для кадра анимации потопления: эти клетки
    временно рисуются указанным символом на обеих досках.
    """
    if profiles is None:
        profiles = await player_profiles(game)

    cells, symbol = highlight if highlight else (set(), None)

    for uid in [game.player1_id, game.player2_id]:
        lang = profiles.get(uid, ('', 'en'))[1]
        player_num = game.get_player_number(uid)

        msgs = game_messages.get(uid)
        if not msgs:
            continue

        own_label = get_translation(lang, 'text_own_ships_field')
        attack_label = get_translation(lang, 'text_attack_field')

        # Своя доска
        own_board = json.loads(game.get_board(player_num))
        display_own = render_own_board(own_board)

        # Доска атаки
        my_attacks = json.loads(game.get_attacks(player_num))
        display_attack = render_attack_board(my_attacks)

        # Кадр анимации: подсвечиваем клетки потопленного корабля на обеих досках
        if symbol:
            for (cx, cy) in cells:
                if display_own.board[cy][cx] in (BANG, BIGBANG):
                    display_own.board[cy][cx] = symbol
                if display_attack.board[cy][cx] in (BANG, BIGBANG):
                    display_attack.board[cy][cx] = symbol

        header = build_board_header(game, uid, lang, profiles)

        bf = ButtonFactory()
        kb = KeyboardBuilder(bf)

        try:
            own_kbd = kb.create_sea_fight_keyboard(display_own, callback_prefix='mpown')
            await bot.edit_message_text(
                chat_id=uid,
                message_id=msgs['own'],
                text=f"{header}\n\n{own_label}",
                reply_markup=own_kbd
            )
        except Exception as e:
            logger.error(f"Error updating own board for {uid}: {e}")

        try:
            attack_kbd = kb.create_sea_fight_keyboard(display_attack, callback_prefix='mpfire')
            await bot.edit_message_text(
                chat_id=uid,
                message_id=msgs['enemy'],
                text=f"{header}\n\n{attack_label}",
                reply_markup=attack_kbd
            )
        except Exception as e:
            logger.error(f"Error updating attack board for {uid}: {e}")


async def animate_mp_sunk(game: MultiplayerGame, ship_cells: set,
                          attacker_num: int, blinks: int = 3):
    """Мигание потопленным кораблём у обоих игроков.

    Запускается фоновой задачей и не задерживает ходы: если за время анимации
    кто-то успел сходить или игра закончилась, оставшиеся кадры пропускаются —
    доску дорисует обычный update_mp_boards.
    """
    if not ship_cells:
        return

    game_id = game.game_id
    baseline = len(json.loads(game.get_attacks(attacker_num)))
    profiles = await player_profiles(game)

    def state_changed() -> bool:
        current = active_games.get(game.player1_id)
        if not current or current.game_id != game_id:
            return True
        if current.status not in ('active', 'finished'):
            return True
        return len(json.loads(current.get_attacks(attacker_num))) != baseline

    try:
        for _ in range(blinks):
            for symbol in (BIGBANG, BANG):
                if state_changed():
                    return
                await update_mp_boards(game, highlight=(ship_cells, symbol), profiles=profiles)
                await asyncio.sleep(DELAY)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error animating sunk ship in game {game_id}: {e}")
    finally:
        # Возвращаем достоверное состояние доски
        if not state_changed():
            try:
                await update_mp_boards(game, profiles=profiles)
            except Exception as e:
                logger.error(f"Error restoring boards after animation: {e}")


# ==================== SINGLE-PLAYER FIRE ====================


@dp.callback_query(F.data.startswith('fire_'))
async def handle_fire(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выстрела"""
    user = callback.from_user
    user_id = user.id

    logger.info(f"Received fire callback: {callback.data} from user {user_id}")

    if user_id not in user_games:
        # Игра потеряна (например, после рестарта бота) — предлагаем начать новую
        language_code = user.language_code or 'en'
        bf = ButtonFactory()
        kb = KeyboardBuilder(bf)
        await edit_message_safe(
            callback.message,
            get_translation(language_code, 'text_game_lost_restart'),
            reply_markup=kb.create_sea_menu_keyboard(language_code)
        )
        await callback.answer()
        return

    game_data = user_games[user_id]
    score = game_data.get('score', 0)
    ship_set = game_data.get('ship_set', 'full')

    # Восстанавливаем состояние игры
    game_logic = GameLogic(
        ROWS, COLS, EMPTY, SHIP,
        initial_board=game_data['board'],
        initial_player_board=game_data['player_board']
    )

    data = callback.data.split('_')
    _, x, y = data
    x = int(x)
    y = int(y)
    # Меняем местами: в клавиатуре fire_{x}_{y}, но board индексируется board[y][x]
    x, y = y, x

    language_code = callback.from_user.language_code or 'en'
    chat_id = callback.message.chat.id
    message_id = callback.message.message_id

    button_factory = ButtonFactory()
    keyboard_builder = KeyboardBuilder(button_factory)

    text = get_translation(language_code, 'text_miss')

    if game_logic.board.is_ship_placed(x, y):
        # Попал
        game_logic.player_board.update_cell(x, y, BANG)
        game_logic.board.update_cell(x, y, BANG)
        score += 10

        if game_logic.check_if_killed(x, y):
            text = get_translation(language_code, 'text_killed')
            await blinking_sea_fight(
                x, y, game_logic.board.board, game_logic.player_board,
                chat_id, message_id, text + f"\n{get_translation(language_code, 'text_score')}: {score}"
            )
        else:
            text = get_translation(language_code, 'text_damaged')

    elif game_logic.board.is_cell_empty(x, y):
        # Мимо — помечаем и на скрытой доске, чтобы повторный клик не снимал очки снова
        game_logic.player_board.update_cell(x, y, MISS)
        game_logic.board.update_cell(x, y, MISS)
        score -= 1
    else:
        # Уже стреляли в эту клетку
        await callback.answer()
        return

    # Обновляем состояние игры
    game_data['board'] = game_logic.board.board
    game_data['player_board'] = game_logic.player_board.board
    game_data['score'] = score

    new_kbd = keyboard_builder.create_sea_fight_keyboard(game_logic.player_board)

    # Проверяем победу
    if game_logic.check_if_won():
        text = get_translation(language_code, 'text_win')
        text = replace_placeholders(text, score)

        try:
            await callback.message.edit_text(
                text=text,
                parse_mode='HTML',
                reply_markup=new_kbd
            )
        except Exception:
            pass

        await bot.send_message(
            chat_id=user_id,
            text=get_translation(language_code, 'text_share_msg')
        )

        share_text = get_translation(language_code, 'text_share_text')
        share_text = replace_placeholders(share_text, score)
        await bot.send_message(
            chat_id=user_id,
            text=share_text,
            parse_mode='HTML'
        )

        # Сразу записываем результат: имя берётся из профиля Telegram
        game_type = 'solo_full' if ship_set == 'full' else 'solo_reduced'
        game_data['game_type'] = game_type

        db_user = await db.get_user(user_id)
        name = display_name(db_user, user_id)
        try:
            position = await db.add_leaderboard_entry(user_id, name, score, game_type)
            added_text = replace_placeholders(
                get_translation(language_code, 'text_leaderboard_added'),
                html.escape(name), position, score
            )
        except Exception as e:
            logger.error(f"Error adding solo leaderboard entry for {user_id}: {e}")
            added_text = get_translation(language_code, 'error_generic')

        await bot.send_message(
            chat_id=user_id,
            text=added_text,
            parse_mode='HTML',
            reply_markup=keyboard_builder.create_sea_menu_keyboard(language_code)
        )
    else:
        text += f"\n{get_translation(language_code, 'text_score')}: {score}"
        try:
            await callback.message.edit_text(
                text=text,
                parse_mode='HTML',
                reply_markup=new_kbd
            )
        except Exception:
            pass

    await callback.answer()


# ==================== LEADERBOARD ====================


@dp.callback_query(F.data == 'leaderboard_show')
async def handle_leaderboard_show(callback: types.CallbackQuery, state: FSMContext):
    """Показать выбор типа лидерборда"""
    language_code = callback.from_user.language_code or 'en'

    bf = ButtonFactory()
    kb = KeyboardBuilder(bf)
    markup = kb.create_leaderboard_type_keyboard(language_code)

    await edit_message_safe(
        callback.message,
        get_translation(language_code, 'text_choose_leaderboard'),
        reply_markup=markup
    )
    await callback.answer()


@dp.callback_query(F.data.startswith('lb_type_'))
async def handle_leaderboard_type(callback: types.CallbackQuery, state: FSMContext):
    """Показать конкретный лидерборд"""
    language_code = callback.from_user.language_code or 'en'

    game_type = callback.data.replace('lb_type_', '')  # solo_full, solo_reduced, mp_full, mp_reduced

    # Метка набора берётся из тех же ключей, что и кнопки выбора таблицы
    type_label = get_translation(language_code, f'leaderboard_{game_type}')
    is_rating = game_type.startswith('mp_')

    text = replace_placeholders(
        get_translation(language_code, 'rating_type_label' if is_rating else 'leaderboard_type_label'),
        html.escape(type_label)
    )

    if is_rating:
        # Мультиплеер — рейтинг игроков, одна строка на игрока
        rows = await db.get_top_ratings(game_type)
        for position, entry in enumerate(rows, start=1):
            name = format_player_name(entry['username'], entry['first_name'],
                                      entry['user_id'])
            text += (f"\n{position}. {html.escape(name)} — {entry['rating']} "
                     f"({entry['games_won']}/{entry['games_lost']})")
    else:
        # Одиночная игра — лучший результат каждого игрока и его дата
        rows = await db.get_top_leaderboard(game_type=game_type)
        for position, entry in enumerate(rows, start=1):
            played = entry['created_at'].strftime('%d.%m.%Y') if entry.get('created_at') else ''
            # lstrip — на случай записей, сохранённых когда имена писались с «@»
            name = (entry['name'] or '').lstrip('@')
            text += f"\n{position}. {html.escape(name)} [{entry['score']}]"
            if played:
                text += f" · {played}"

    if not rows:
        text += "\n—"

    # Кнопка назад к выбору типа + возврат в главное меню
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=get_translation(language_code, 'btn_back'),
            callback_data='leaderboard_show'
        )],
        [InlineKeyboardButton(
            text=get_translation(language_code, 'btn_main_menu'),
            callback_data='menu'
        )]
    ])

    try:
        await edit_message_safe(callback.message, text, reply_markup=markup,
                                parse_mode='HTML')
    except Exception:
        pass

    await callback.answer()


async def main():
    """Запуск бота"""
    global games_manager

    # Подключаемся к базе данных
    await db.connect()
    await db.init_tables()

    # Игры ядра: SQLite рядом с ботом; обработчики — после обработчиков морского боя
    Path(config.GAMES_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    games_storage = Storage(config.GAMES_DB_PATH)
    games_manager = games_tg.build_manager(bot, games_storage)
    games_tg.register(dp, bot, games_manager)

    # Восстанавливаем активные игры и их таймеры после рестарта
    try:
        for game_data in await db.get_all_active_games():
            game = MultiplayerGame(**game_data)
            active_games[game.player1_id] = game
            if game.player2_id:
                active_games[game.player2_id] = game
            start_turn_timer(game)
    except Exception as e:
        logger.error(f"Error restoring active games: {e}")

    me = await bot.get_me()
    logger.info("started as @%s (id %s), games db=%s", me.username, me.id, config.GAMES_DB_PATH)

    try:
        await dp.start_polling(bot)
    finally:
        await games_manager.shutdown()
        games_storage.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
