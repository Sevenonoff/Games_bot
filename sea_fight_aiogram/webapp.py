"""Сервер Telegram Mini App: статика, картинки экранов и WebSocket к Manager ядра.

Протокол и контракт — docs/miniapp/README.md §4 и tz-m1-core.md. Коротко:
  клиент → {"type": "hello", "initData": …, "start": …} — вход (подпись initData проверяется);
           {"type": "press", "payload": "new:memo", "seq": 7} — нажатие, те же payload'ы, что у кнопок бота;
  сервер → {"type": "screen", "seq": 7 | null, "note": …, "screen": {text, rows, image, view}} —
           ответ на нажатие (seq как в нём) или правка по таймеру (seq null);
           {"type": "notice", "screen": …} — бот сам пишет игроку (в чате — новое сообщение);
           {"type": "error", "code": …}.

Место показа Mini App для Manager — msg_ref ("web", conn_id): на соединении один экран, любой ответ
«правит» его, как нажатие в чате правит своё сообщение. Без aiogram: тесты ядра гоняют его в .venv.
"""
import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set

from aiohttp import WSMsgType, web

from games_core import debug
from games_core.manager import start_payload
from games_core.sessions import Player
from games_core.ui import MAX_DATA_LEN, Screen, image_filename

try:                                    # запуск из папки бота (main.py) и импорт пакетом (тесты)
    import initdata
except ImportError:                     # pragma: no cover
    from sea_fight_aiogram import initdata

logger = logging.getLogger("webapp")

LOCAL = ("127.0.0.1", "::1")
IMAGES_KEPT = 300
MAX_MESSAGE = 16 * 1024


def is_ref(ref: Any) -> bool:
    """msg_ref экрана Mini App (а не сообщения в чате)."""
    return isinstance(ref, tuple) and len(ref) == 2 and ref[0] == "web"


@dataclass(eq=False)
class Conn:
    id: int
    ws: web.WebSocketResponse
    player: Player
    opened: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def ref(self):
        return ("web", self.id)

    async def send(self, message: dict) -> None:
        if self.ws.closed:
            return
        async with self.lock:           # кадры ответа и правок по таймеру не перемешиваются
            try:
                await self.ws.send_str(json.dumps(message, ensure_ascii=False))
            except (ConnectionError, RuntimeError) as e:
                logger.debug("ws send failed: conn %s: %s", self.id, e)


class WebApp:
    """manager выставляется после создания: Manager получает push этого сервера, а сервер — Manager."""

    def __init__(self, *, bot_token: str, make_player: Callable[[dict], Player],
                 static_dir: Optional[Path] = None, dev: bool = False, clock: Callable[[], float] = time.time):
        self.bot_token = bot_token
        self.make_player = make_player
        self.static_dir = Path(static_dir) if static_dir else None
        self.dev = dev
        self.clock = clock
        self.manager = None
        self.conns: Dict[int, Conn] = {}
        self.by_user: Dict[int, Set[int]] = {}
        self.images: "OrderedDict[str, bytes]" = OrderedDict()
        self._ids = count(1)

    # --- приложение aiohttp ---

    def app(self) -> web.Application:
        app = web.Application(client_max_size=MAX_MESSAGE)
        app.router.add_get("/ws", self.ws_handler)
        app.router.add_get("/img/{name}", self.image_handler)
        app.router.add_get("/", self.to_app)
        app.router.add_get("/app", self.to_app)
        app.router.add_get("/app/", self.index_handler)
        assets = self.static_dir / "assets" if self.static_dir else None
        if assets is not None and assets.is_dir():
            app.router.add_static("/app/assets/", assets, append_version=False)
        if self.dev:
            app.router.add_get("/dev/hint", self.hint_handler)
        return app

    @staticmethod
    async def to_app(request: web.Request) -> web.Response:
        raise web.HTTPFound("/app/")

    async def index_handler(self, request: web.Request) -> web.StreamResponse:
        index = self.static_dir / "index.html" if self.static_dir else None
        if index is None or not index.is_file():
            return web.Response(status=503, text="Mini App ещё не собран: cd miniapp && npm run build")
        return web.FileResponse(index, headers={"Cache-Control": "no-cache"})

    async def image_handler(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        image = self.images.get(name.split(".")[0])
        if image is None:
            raise web.HTTPNotFound()
        kind = "image/jpeg" if image[:2] == b"\xff\xd8" else "image/png"
        return web.Response(body=image, content_type=kind,
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})

    async def hint_handler(self, request: web.Request) -> web.Response:
        """Только в dev-режиме: верный ход игрока — e2e-тесты фронтенда ходят по нему."""
        if request.remote not in LOCAL:
            raise web.HTTPForbidden()
        try:
            uid = int(request.query["user"])
        except (KeyError, ValueError):
            raise web.HTTPBadRequest()
        async with self.manager.locks[uid]:
            payload = debug.hint_payload(self.manager, uid)
        return web.json_response({"payload": payload})

    # --- экраны ---

    def serialize(self, screen: Screen) -> dict:
        image = None
        if screen.image is not None:
            digest = hashlib.sha1(screen.image).hexdigest()
            self.images[digest] = screen.image
            self.images.move_to_end(digest)
            while len(self.images) > IMAGES_KEPT:
                self.images.popitem(last=False)
            image = f"/img/{digest}.{image_filename(screen.image).rsplit('.', 1)[1]}"
        return {"text": screen.text,
                "rows": [[{"text": b.text, "data": b.data} for b in row] for row in screen.rows],
                "image": image, "view": screen.view}

    async def push(self, ref, screen: Screen) -> None:
        """Правка по таймеру (Manager.push): экран соединения обновляется; закрытого — нет."""
        conn = self.conns.get(ref[1])
        if conn is not None:
            await conn.send({"type": "screen", "seq": None, "note": None, "screen": self.serialize(screen)})

    async def notice(self, user_id: int, screen: Screen) -> None:
        """Бот сам пишет игроку: в Mini App — всплывающая карточка во всех его открытых окнах."""
        for conn_id in list(self.by_user.get(user_id, ())):
            conn = self.conns.get(conn_id)
            if conn is not None:
                await conn.send({"type": "notice", "screen": self.serialize(screen)})

    def online(self, user_id: int) -> bool:
        return bool(self.by_user.get(user_id))

    # --- соединение ---

    def _auth(self, hello: dict, request: web.Request) -> Optional[Player]:
        user = initdata.verify(hello.get("initData") or "", self.bot_token, self.clock())
        if user is None and self.dev and request.remote in LOCAL and isinstance(hello.get("dev_user"), dict):
            dev_user = hello["dev_user"]
            if isinstance(dev_user.get("id"), int):
                user = {"id": dev_user["id"], "first_name": str(dev_user.get("name") or dev_user["id"])}
        return self.make_player(user) if user is not None else None

    async def ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30, max_msg_size=MAX_MESSAGE)
        await ws.prepare(request)
        conn: Optional[Conn] = None
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                    kind = data["type"]
                except (ValueError, KeyError, TypeError):
                    await self._error(ws, "bad_request")
                    continue
                if conn is None:
                    if kind != "hello":
                        await self._error(ws, "bad_request", "сначала hello")
                        continue
                    player = self._auth(data, request)
                    if player is None:
                        logger.info("ws auth failed from %s", request.remote)
                        await self._error(ws, "auth")
                        break
                    conn = self._open(ws, player)
                    start = data.get("start")
                    await self._handle(conn, start_payload(start) if isinstance(start, str) else "menu", None)
                elif kind == "press":
                    payload, seq = data.get("payload"), data.get("seq")
                    if not isinstance(payload, str) or not payload or len(payload) > MAX_DATA_LEN \
                            or not (seq is None or isinstance(seq, int)):
                        await self._error(ws, "bad_request")
                        continue
                    await self._handle(conn, payload, seq)
                else:
                    await self._error(ws, "bad_request")
        finally:
            if conn is not None:
                self._close(conn)
        return ws

    def _open(self, ws: web.WebSocketResponse, player: Player) -> Conn:
        conn = Conn(next(self._ids), ws, player, self.clock())
        self.conns[conn.id] = conn
        self.by_user.setdefault(player.user_id, set()).add(conn.id)
        logger.info("ws open conn=%s user=%s", conn.id, player.user_id)
        return conn

    def _close(self, conn: Conn) -> None:
        self.conns.pop(conn.id, None)
        ids = self.by_user.get(conn.player.user_id)
        if ids is not None:
            ids.discard(conn.id)
            if not ids:
                del self.by_user[conn.player.user_id]
        logger.info("ws close conn=%s user=%s s=%d", conn.id, conn.player.user_id, self.clock() - conn.opened)

    async def _handle(self, conn: Conn, payload: str, seq: Optional[int]) -> None:
        started = time.monotonic()
        note = []

        async def respond(reply):
            note.append(reply.note)
            await conn.send({"type": "screen", "seq": seq, "note": reply.note,
                             "screen": self.serialize(reply.screen) if reply.screen is not None else None})
            return conn.ref if reply.screen is not None else None

        try:
            await self.manager.handle(conn.player, payload, respond)
        except Exception:
            logger.exception("ws handle failed: user=%s payload=%r", conn.player.user_id, payload)
            await conn.send({"type": "error", "code": "server", "seq": seq})
        logger.info("tap user=%s payload=%s via=web ms=%d note=%r", conn.player.user_id, payload,
                    (time.monotonic() - started) * 1000, note[0] if note else None)

    @staticmethod
    async def _error(ws: web.WebSocketResponse, code: str, message: str = "") -> None:
        if not ws.closed:
            await ws.send_str(json.dumps({"type": "error", "code": code, "message": message}, ensure_ascii=False))
