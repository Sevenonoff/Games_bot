"""Подписка бота на webhook Max.

    python -m max_bot.webhook list           подписки бота
    python -m max_bot.webhook subscribe      подписать WEBHOOK_URL (main делает это сам при старте)
    python -m max_bot.webhook unsubscribe    снять подписку на WEBHOOK_URL — вернуться к long polling

Пока у бота есть подписка, long polling ничего не получает. Max шлёт только на HTTPS:443,
ждёт 200 до 30 с и снимает подписку сам, если 8 ч подряд нет 200.
"""
import asyncio
import sys

from maxapi import Bot
from maxapi.enums.update import UpdateType

from . import config

UPDATE_TYPES = [UpdateType.BOT_STARTED, UpdateType.MESSAGE_CREATED, UpdateType.MESSAGE_CALLBACK]


def mask(text: str) -> str:
    return text.replace(config.WEBHOOK_SECRET, "***") if config.WEBHOOK_SECRET else text


async def subscribed_urls(bot: Bot) -> list[str]:
    return [s.url for s in (await bot.get_subscriptions()).subscriptions]


async def ensure_subscribed(bot: Bot) -> bool:
    """Подписать WEBHOOK_URL, если ещё не подписан. True — подписали сейчас."""
    if config.WEBHOOK_URL in await subscribed_urls(bot):
        return False
    await bot.subscribe_webhook(config.WEBHOOK_URL, update_types=UPDATE_TYPES, secret=config.WEBHOOK_SECRET)
    return True


async def main(action: str) -> None:
    bot = Bot(config.MAX_BOT_TOKEN)
    try:
        if action == "subscribe":
            print("subscribed" if await ensure_subscribed(bot) else "already subscribed")
        elif action == "unsubscribe":
            await bot.unsubscribe_webhook(config.WEBHOOK_URL)
            print("unsubscribed")
        print("subscriptions:", [mask(u) for u in await subscribed_urls(bot)])
    finally:
        await bot.close_session()


if __name__ == "__main__":
    act = sys.argv[1] if len(sys.argv) > 1 else "list"
    if act not in ("list", "subscribe", "unsubscribe"):
        raise SystemExit(__doc__)
    if act != "list" and not (config.WEBHOOK_URL and config.WEBHOOK_SECRET):
        raise SystemExit("WEBHOOK_URL и WEBHOOK_SECRET не заданы (max_bot/.env)")
    asyncio.run(main(act))
