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
from aiohttp import web

# Ядро — из корня репозитория. append, а не insert: корень не должен перекрывать config бота
sys.path.append(str(Path(__file__).resolve().parent.parent))
from games_core.storage import Storage  # noqa: E402

import config  # noqa: E402
import games_tg  # noqa: E402
import webapp  # noqa: E402

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
    app = webapp.WebApp(bot_token=config.BOT_TOKEN, make_player=games_tg.player_from_webapp,
                        static_dir=Path(config.MINIAPP_STATIC), dev=config.MINIAPP_DEV)
    manager = games_tg.build_manager(bot, storage, me.username, webapp=app)
    app.manager = manager
    runner = None
    if config.MINIAPP_PORT:
        runner = web.AppRunner(app.app(), access_log=None)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", int(config.MINIAPP_PORT)).start()
        logger.info("mini app on 127.0.0.1:%s, static=%s, dev=%s", config.MINIAPP_PORT,
                    config.MINIAPP_STATIC, config.MINIAPP_DEV)
    dp = Dispatcher()
    games_tg.register(dp, bot, manager)
    restored = manager.restore()
    manager.start_background()
    logger.info("started as @%s (id %s), db=%s, restored mp games: %d",
                me.username, me.id, config.GAMES_DB_PATH, restored)
    try:
        await dp.start_polling(bot)
    finally:
        if runner is not None:
            await runner.cleanup()
        await manager.shutdown()
        storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
