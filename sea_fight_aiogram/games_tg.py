"""Telegram-транспорт для Manager ядра games_core (по образцу max_bot/main.py).

Manager выдаёт Screen, здесь он превращается в сообщение Telegram. Ссылка на
сообщение для правок по таймеру — (chat_id, message_id).
"""
import logging
import time
from typing import Optional

from aiogram import Bot, Dispatcher, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from games_core.manager import Manager, start_payload, text_payload
from games_core.sessions import Player
from games_core.storage import Storage
from games_core.texts import t
from games_core.ui import Reply, Screen

import config
from games_menu import PLATFORM, core_payload, format_player_name, tg_rows

logger = logging.getLogger("games_tg")

HTML = "HTML"


def render(screen: Screen) -> Optional[InlineKeyboardMarkup]:
    rows = tg_rows(screen)
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=cb) for text, cb in row] for row in rows])


def make_player(user_id: int, username: Optional[str], first_name: Optional[str], chat_id: int) -> Player:
    return Player(PLATFORM, user_id, format_player_name(username, first_name, user_id)[:64], chat_id)


def player_from(user: types.User, chat_id: Optional[int] = None) -> Player:
    return make_player(user.id, user.username, user.first_name, chat_id or user.id)


def not_modified(e: TelegramBadRequest) -> bool:
    return "message is not modified" in str(e)


async def send_screen(bot: Bot, chat_id: int, screen: Screen):
    sent = await bot.send_message(chat_id=chat_id, text=screen.text,
                                  reply_markup=render(screen), parse_mode=HTML)
    return sent.chat.id, sent.message_id


def new_message_sender(bot: Bot, chat_id: int):
    """respond для текстовых команд: экран уходит новым сообщением."""
    async def respond(reply: Reply):
        if reply.screen is None:
            return None
        return await send_screen(bot, chat_id, reply.screen)
    return respond


def callback_responder(bot: Bot, callback: types.CallbackQuery, timing: dict):
    """respond для нажатий: правка сообщения с кнопкой, затем ответ на callback (уведомление)."""
    async def respond(reply: Reply):
        timing["dispatched"] = time.monotonic()
        timing["note"] = reply.note
        try:
            ref = await _show(reply.screen) if reply.screen is not None else None
            try:
                await callback.answer(text=reply.note)
            except TelegramBadRequest as e:
                # callback старше ~15 с Telegram уже не принимает — это не ошибка игры
                logger.debug("answer failed: %s", e)
            return ref
        finally:
            timing["answered"] = time.monotonic()

    async def _show(screen: Screen):
        message = callback.message
        # фото (старое меню с картинкой) и сообщения старше 48 ч не правятся текстом — шлём новое
        if isinstance(message, types.Message) and not message.photo:
            try:
                await message.edit_text(text=screen.text, reply_markup=render(screen), parse_mode=HTML)
            except TelegramBadRequest as e:
                if not not_modified(e):
                    raise
            return message.chat.id, message.message_id
        chat_id = message.chat.id if message is not None else callback.from_user.id
        return await send_screen(bot, chat_id, screen)
    return respond


def build_manager(bot: Bot, storage: Storage, bot_username: str = "") -> Manager:
    async def push(ref, screen: Screen) -> None:
        chat_id, message_id = ref
        try:
            await bot.edit_message_text(text=screen.text, chat_id=chat_id, message_id=message_id,
                                        reply_markup=render(screen), parse_mode=HTML)
        except TelegramBadRequest as e:
            if not not_modified(e):
                raise

    async def send(chat_id: int, screen: Screen):
        """Бот сам пишет игроку (бой с другом: соперник подключился, сдался…)."""
        return await send_screen(bot, chat_id, screen)

    def start_link(param: str) -> str:
        return f"https://t.me/{bot_username}?start={param}"

    return Manager(storage, PLATFORM, push, send=send, start_link=start_link,
                   preview_seconds=config.PREVIEW_SECONDS, round_seconds=config.ROUND_SECONDS,
                   countdown_seconds=config.COUNTDOWN_SECONDS, tick_seconds=config.TIMER_TICK_SECONDS,
                   memo_close_seconds=config.MEMO_CLOSE_SECONDS, review_seconds=config.REVIEW_SECONDS,
                   mp_blink_seconds=config.MP_BLINK_SECONDS, debug_users=config.DEBUG_USER_IDS)


async def safe_handle(manager: Manager, player: Player, payload: str, respond) -> None:
    try:
        await manager.handle(player, payload, respond)
    except Exception:
        logger.exception("handle failed: user=%s payload=%r", player.user_id, payload)


def register(dp: Dispatcher, bot: Bot, manager: Manager) -> None:
    async def on_callback(callback: types.CallbackQuery, payload: str) -> None:
        chat_id = callback.message.chat.id if callback.message else None
        received = time.monotonic()
        timing: dict = {}
        await safe_handle(manager, player_from(callback.from_user, chat_id), payload,
                          callback_responder(bot, callback, timing))
        done = time.monotonic()
        dispatched = timing.get("dispatched", done)
        # wait — очередь за замком игрока (таймеры, предыдущие нажатия), api — ответ Telegram
        logger.info("tap user=%s payload=%s wait=%dms api=%dms note=%r",
                    callback.from_user.id, payload, (dispatched - received) * 1000,
                    (timing.get("answered", done) - dispatched) * 1000, timing.get("note"))

    @dp.callback_query(F.data.startswith("g:"))
    async def on_core_callback(callback: types.CallbackQuery):
        await on_callback(callback, core_payload(callback.data))

    @dp.callback_query()
    async def on_old_callback(callback: types.CallbackQuery):
        # кнопки aiogram-версии до 2.0.0 (fire_…, mpfire_…, menu…) в старых сообщениях
        try:
            await callback.answer(text=t("note_old_button"))
        except TelegramBadRequest as e:
            logger.debug("answer failed: %s", e)

    @dp.message(CommandStart())
    async def on_start(message: types.Message, command: CommandObject):
        # ссылки https://t.me/<бот>?start=mp_<код> (бой) и fr_<код> (друзья) приходят как «/start <param>»
        await safe_handle(manager, player_from(message.from_user, message.chat.id),
                          start_payload(command.args), new_message_sender(bot, message.chat.id))

    @dp.message()
    async def on_message(message: types.Message):
        if message.from_user is None or message.from_user.is_bot:
            return
        await safe_handle(manager, player_from(message.from_user, message.chat.id),
                          text_payload(message.text), new_message_sender(bot, message.chat.id))
