"""Бот игр для Telegram (@games_telegram_robot): все игры — ядро games_core, как в Max.

Запуск: python run.py (из этой папки). Транспорт — games_tg.py.
До 2.0.0 здесь жил собственный морской бой на aiogram + PostgreSQL; его рейтинги
и рекорды перенесены в SQLite скриптом deploy/migrate_postgres.py.
"""
import asyncio
import logging
import logging.handlers
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher

# Ядро — из корня репозитория. append, а не insert: корень не должен перекрывать config бота
sys.path.append(str(Path(__file__).resolve().parent.parent))
from games_core.storage import Storage  # noqa: E402

import config  # noqa: E402
import games_tg  # noqa: E402

logger = logging.getLogger("main")


def setup_logging() -> None:
    """LOG_FILE — файл с ротацией, иначе stdout."""
    if config.LOG_FILE:
        Path(config.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        handlers = [logging.handlers.RotatingFileHandler(
            config.LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")]
    else:
        handlers = [logging.StreamHandler(sys.stdout)]
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def main() -> None:
    setup_logging()
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан. Создайте файл .env по образцу .env.example")
    Path(config.GAMES_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    storage = Storage(config.GAMES_DB_PATH)
    bot = Bot(token=config.BOT_TOKEN)
    me = await bot.get_me()
    manager = games_tg.build_manager(bot, storage, me.username)
    dp = Dispatcher()
    games_tg.register(dp, bot, manager)
    restored = manager.restore()
    manager.start_background()
    logger.info("started as @%s (id %s), db=%s, restored mp games: %d",
                me.username, me.id, config.GAMES_DB_PATH, restored)
    try:
        await dp.start_polling(bot)
    finally:
        await manager.shutdown()
        storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
