"""Dev-сервер Mini App: тот же webapp.WebApp и Manager ядра, но без Telegram.

Не поллит бота (один поллер на токен — боевой games-tg-bot), вход только dev_user с localhost,
своя БД. Для разработки фронтенда и e2e-тестов (docs/miniapp/tz-m1-core.md §2.6):
    miniapp/dev-server.sh            # http://127.0.0.1:8448/app/, ws://127.0.0.1:8448/ws
Переменные: DEV_PORT (8448), DEV_DB (miniapp/dev.db), DEV_ADMINS (id с /dbg: «1», «1 2», «1-4 300-399»),
MINIAPP_STATIC.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from aiohttp import web  # noqa: E402

from games_core.manager import Manager  # noqa: E402
from games_core.sessions import Player  # noqa: E402
from games_core.storage import Storage  # noqa: E402

import webapp  # noqa: E402
from games_menu import PLATFORM, format_player_name  # noqa: E402


def parse_ids(text: str) -> list:
    """«1, 2 300-302» → [1, 2, 300, 301, 302]: id и диапазоны через пробел или запятую."""
    ids = []
    for part in text.replace(",", " ").split():
        lo, _, hi = part.partition("-")
        ids.extend(range(int(lo), int(hi or lo) + 1))
    return ids


def make_player(user: dict) -> Player:
    return Player(PLATFORM, user["id"], format_player_name(user.get("username"), user.get("first_name"), user["id"]),
                  user["id"])


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    port = int(os.getenv("DEV_PORT", "8448"))
    db = Path(os.getenv("DEV_DB", str(HERE.parent / "miniapp" / "dev.db")))
    db.parent.mkdir(parents=True, exist_ok=True)
    static = Path(os.getenv("MINIAPP_STATIC", str(HERE.parent / "miniapp" / "dist")))
    admins = parse_ids(os.getenv("DEV_ADMINS", "1"))

    app = webapp.WebApp(bot_token="", make_player=make_player, static_dir=static, dev=True)

    async def send(chat_id: int, screen):
        await app.notice(chat_id, screen)       # чата нет: только карточка в Mini App

    storage = Storage(str(db))
    manager = Manager(storage, PLATFORM, app.push, send=send, debug_users=admins, live_ref=webapp.is_ref,
                      start_link=lambda param: f"https://t.me/dev_bot?start={param}")
    app.manager = manager
    manager.restore()
    manager.start_background()
    runner = web.AppRunner(app.app())
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    logging.info("dev mini app: http://127.0.0.1:%s/app/  db=%s  admins=%s", port, db, os.getenv("DEV_ADMINS", "1"))
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await manager.shutdown()
        storage.close()


if __name__ == "__main__":
    asyncio.run(main())
