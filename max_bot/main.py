"""Бот игр для мессенджера Max (long polling).

Запуск из корня репозитория: python -m max_bot.main
"""
import asyncio
import logging
import logging.handlers
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from maxapi import Bot, Dispatcher
from maxapi.enums.parse_mode import ParseMode
from maxapi.types import BotStarted, CallbackButton, MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from games_core.manager import Manager, text_payload
from games_core.sessions import Player
from games_core.storage import Storage
from games_core.ui import Reply, Screen

from . import config, webhook

logger = logging.getLogger("max_bot")


class SecretFilter(logging.Filter):
    """Маскирует секрет вебхука в любой строке лога (maxapi пишет URL вебхука целиком)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if config.WEBHOOK_SECRET:
            message = record.getMessage()
            if config.WEBHOOK_SECRET in message:
                record.msg, record.args = message.replace(config.WEBHOOK_SECRET, "***"), None
        return True


def setup_logging() -> None:
    if config.LOG_FILE:
        Path(config.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        handlers = [logging.handlers.RotatingFileHandler(
            config.LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")]
    else:
        handlers = [logging.StreamHandler(sys.stdout)]
    for handler in handlers:
        handler.addFilter(SecretFilter())
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
                                      attachments=render(reply.screen), format=ParseMode.HTML)
        return message_id(sent.message) if sent else None
    return respond


def callback_responder(event: MessageCallback, timing: dict):
    """respond для нажатий: ответ на callback и правка сообщения одним запросом."""
    async def respond(reply: Reply):
        timing["dispatched"] = time.monotonic()
        timing["note"] = reply.note
        try:
            return await _respond(reply)
        finally:
            timing["answered"] = time.monotonic()

    async def _respond(reply: Reply):
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
                               attachments=render(screen), format=ParseMode.HTML)

    manager = Manager(storage, config.PLATFORM, push,
                      preview_seconds=config.PREVIEW_SECONDS, round_seconds=config.ROUND_SECONDS,
                      countdown_seconds=config.COUNTDOWN_SECONDS, tick_seconds=config.TIMER_TICK_SECONDS,
                      memo_close_seconds=config.MEMO_CLOSE_SECONDS,
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
        received = time.monotonic()
        # возраст нажатия к приходу к нам: callback.timestamp ставит сервер Max (мс)
        age_ms = int(time.time() * 1000) - event.callback.timestamp
        timing: dict = {}
        payload = event.callback.payload or "menu"
        await safe_handle(player_from(event.callback.user, chat_id), payload,
                          callback_responder(event, timing))
        done = time.monotonic()
        dispatched = timing.get("dispatched", done)
        # wait — очередь за замком игрока (таймеры, предыдущие нажатия), api — ответ Max
        logger.info("tap user=%s payload=%s age=%dms wait=%dms api=%dms note=%r",
                    event.callback.user.user_id, payload, age_ms,
                    (dispatched - received) * 1000, (timing.get("answered", done) - dispatched) * 1000,
                    timing.get("note"))

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
        if config.WEBHOOK_URL:
            if not config.WEBHOOK_SECRET:
                raise SystemExit("WEBHOOK_URL задан без WEBHOOK_SECRET")
            if await webhook.ensure_subscribed(bot):
                logger.info("subscribed webhook %s", webhook.mask(config.WEBHOOK_URL))
            logger.info("webhook mode on %s:%s", config.WEBHOOK_HOST, config.WEBHOOK_PORT)
            # access_log=None: путь вебхука содержит секрет
            await dp.handle_webhook(bot, host=config.WEBHOOK_HOST, port=config.WEBHOOK_PORT,
                                    path=urlparse(config.WEBHOOK_URL).path, secret=config.WEBHOOK_SECRET,
                                    access_log=None)
        else:
            subs = await webhook.subscribed_urls(bot)
            if subs:
                logger.warning("polling, но у бота есть webhook-подписки %s — апдейты уйдут туда; "
                               "снять: python -m max_bot.webhook unsubscribe", [webhook.mask(u) for u in subs])
            logger.info("long polling mode")
            await dp.start_polling(bot)
    finally:
        await manager.shutdown()
        storage.close()


if __name__ == "__main__":
    asyncio.run(main())
