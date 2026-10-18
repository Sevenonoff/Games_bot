"""Бот игр для мессенджера Max (long polling).

Запуск из корня репозитория: python -m max_bot.main
"""
import asyncio
import logging
import logging.handlers
import sys
from pathlib import Path

from maxapi import Bot, Dispatcher
from maxapi.enums.parse_mode import ParseMode
from maxapi.types import BotStarted, CallbackButton, MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from games_core.manager import Manager, text_payload
from games_core.sessions import Player
from games_core.storage import Storage
from games_core.ui import Reply, Screen

from . import config

logger = logging.getLogger("max_bot")


def setup_logging() -> None:
    if config.LOG_FILE:
        Path(config.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        handlers = [logging.handlers.RotatingFileHandler(
            config.LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")]
    else:
        handlers = [logging.StreamHandler(sys.stdout)]
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def render(screen: Screen) -> list:
    if not screen.rows:
        return []
    kb = InlineKeyboardBuilder()
    for row in screen.rows:
        kb.row(*[CallbackButton(text=b.text, payload=b.data) for b in row])
    return [kb.as_markup()]


def player_from(user, chat_id) -> Player:
    name = " ".join(x for x in (user.first_name, user.last_name) if x) or user.username or str(user.user_id)
    return Player(config.PLATFORM, user.user_id, name[:64], chat_id)


def message_id(message) -> str | None:
    if message is None or message.body is None:
        return None
    return message.body.mid


def main_screen_sender(bot: Bot, chat_id: int):
    """respond для текстовых команд: экран уходит новым сообщением."""
    async def respond(reply: Reply):
        if reply.screen is None:
            return None
        sent = await bot.send_message(chat_id=chat_id, text=reply.screen.text,
                                      attachments=render(reply.screen), parse_mode=ParseMode.HTML)
        return message_id(sent.message) if sent else None
    return respond


def callback_responder(event: MessageCallback):
    """respond для нажатий: ответ на callback и правка сообщения одним запросом."""
    async def respond(reply: Reply):
        if reply.screen is None:
            try:
                await event.ack(notification=reply.note)
            except Exception as e:
                # пустой ответ (без уведомления) API может отклонить — это не ошибка игры
                logger.debug("ack failed: %s", e)
            return None
        await event.edit(text=reply.screen.text, attachments=render(reply.screen),
                         format=ParseMode.HTML, notification=reply.note, notify=False)
        return message_id(event.message)
    return respond


def build(bot: Bot, storage: Storage) -> tuple[Dispatcher, Manager]:
    dp = Dispatcher(use_create_task=True)

    async def push(ref, screen: Screen) -> None:
        await bot.edit_message(message_id=ref, text=screen.text,
                               attachments=render(screen), parse_mode=ParseMode.HTML)

    manager = Manager(storage, config.PLATFORM, push,
                      preview_seconds=config.PREVIEW_SECONDS, round_seconds=config.ROUND_SECONDS,
                      debug_users=config.DEBUG_USER_IDS)

    async def safe_handle(player: Player, payload: str, respond) -> None:
        try:
            await manager.handle(player, payload, respond)
        except Exception:
            logger.exception("handle failed: user=%s payload=%r", player.user_id, payload)

    @dp.bot_started()
    async def on_bot_started(event: BotStarted):
        await safe_handle(player_from(event.user, event.chat_id), "menu",
                          main_screen_sender(bot, event.chat_id))

    @dp.message_created()
    async def on_message(event: MessageCreated):
        sender = event.message.sender
        if sender is None or sender.is_bot:
            return
        chat_id = event.message.recipient.chat_id
        text = event.message.body.text if event.message.body else None
        await safe_handle(player_from(sender, chat_id), text_payload(text), main_screen_sender(bot, chat_id))

    @dp.message_callback()
    async def on_callback(event: MessageCallback):
        chat_id = event.message.recipient.chat_id if event.message else None
        await safe_handle(player_from(event.callback.user, chat_id),
                          event.callback.payload or "menu", callback_responder(event))

    return dp, manager


async def main() -> None:
    setup_logging()
    if not config.MAX_BOT_TOKEN:
        raise SystemExit("MAX_BOT_TOKEN не задан (max_bot/.env)")
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    storage = Storage(config.DB_PATH)
    bot = Bot(config.MAX_BOT_TOKEN)
    dp, manager = build(bot, storage)
    me = await bot.get_me()
    logger.info("started as @%s (id %s), db=%s", me.username, me.user_id, config.DB_PATH)
    try:
        await dp.start_polling(bot)
    finally:
        await manager.shutdown()
        storage.close()


if __name__ == "__main__":
    asyncio.run(main())
