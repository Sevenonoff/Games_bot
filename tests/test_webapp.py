"""Сервер Mini App: WebSocket к Manager ядра на виртуальном времени, протокол из docs/miniapp/README.md §4."""
import asyncio
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from games_core.sessions import Player
from sea_fight_aiogram import webapp
from tests.harness import World, mp_game
from tests.test_initdata import TOKEN, make_init_data


def make_player(user: dict) -> Player:
    return Player("tg", user["id"], user.get("username") or user.get("first_name") or str(user["id"]), user["id"])


class WebClient:
    """Окно Mini App: шлёт hello/press, копит кадры; screen — последний показанный экран."""

    def __init__(self, ws):
        self.ws = ws
        self.seq = 0
        self.frames = []
        self.screen = None
        self.notes = []
        self.notices = []
        self.errors = []
        self._reader = asyncio.create_task(self._read())

    async def _read(self):
        async for msg in self.ws:
            frame = json.loads(msg.data)
            self.frames.append(frame)
            if frame["type"] == "screen":
                if frame["screen"] is not None:
                    self.screen = frame["screen"]
                self.notes.append(frame["note"])
            elif frame["type"] == "notice":
                self.notices.append(frame["screen"])
            elif frame["type"] == "error":
                self.errors.append(frame)

    async def wait(self, cond, what="кадр", rounds=200):
        for _ in range(rounds):
            if cond():
                return
            await asyncio.sleep(0.005)
        raise AssertionError(f"не дождались: {what}; последние кадры: {self.frames[-3:]}")

    async def send(self, message: dict):
        await self.ws.send_str(json.dumps(message))

    async def hello(self, **fields):
        n = len(self.frames)
        await self.send({"type": "hello", **fields})
        await self.wait(lambda: len(self.frames) > n, "ответ на hello")
        return self.frames[-1]

    async def press(self, payload: str) -> dict:
        self.seq += 1
        seq = self.seq
        await self.send({"type": "press", "payload": payload, "seq": seq})
        await self.wait(lambda: any(f.get("seq") == seq for f in self.frames), f"ответ на {payload}")
        return next(f for f in self.frames if f.get("seq") == seq)

    @property
    def view(self):
        return self.screen["view"] if self.screen else None

    def action(self, name: str, **xy) -> str:
        payload = self.view["actions"][name]
        for k, v in xy.items():
            payload = payload.replace("{" + k + "}", str(v))
        return payload

    def find(self, text: str) -> str:
        found = [b["data"] for row in self.screen["rows"] for b in row if text in b["text"]]
        assert len(found) == 1, (text, [b["text"] for row in self.screen["rows"] for b in row])
        return found[0]


@pytest.fixture
async def env():
    """Мир харнесса (Manager на виртуальном времени, чаты) + сервер Mini App на тот же Manager:
    правки экранов Mini App идут в WebSocket, сообщения в чат — в мессенджер харнесса."""
    world = World(platform="tg")
    world.time.now = 1_800_000_000.0           # initData проверяется по часам Manager
    app = webapp.WebApp(bot_token=TOKEN, make_player=make_player, dev=True, clock=world.time)
    mgr = world.mgr
    chat_push, chat_send = mgr.push, mgr.send

    async def push(ref, screen):
        if webapp.is_ref(ref):
            await app.push(ref, screen)
        else:
            await chat_push(ref, screen)

    async def send(chat_id, screen):
        await app.notice(chat_id, screen)
        return await chat_send(chat_id, screen)

    mgr.push, mgr.send, mgr.live_ref = push, send, webapp.is_ref
    app.manager = mgr
    client = TestClient(TestServer(app.app()))
    await client.start_server()
    clients = []

    async def connect(**hello) -> WebClient:
        c = WebClient(await client.ws_connect("/ws"))
        clients.append(c)
        if hello:
            await c.hello(**hello)
        return c

    yield world, app, client, connect
    for c in clients:
        await c.ws.close()
    await client.close()
    await world.close()
    assert not world.errors, world.errors


async def test_hello_with_signed_init_data_shows_menu_and_image(env):
    world, app, client, connect = env
    web = await connect(initData=make_init_data(user={"id": 7, "first_name": "Аня"}, auth_date=int(world.time.now)))
    assert "Выберите игру" in web.screen["text"]
    assert web.screen["view"] is None and web.screen["image"].startswith("/img/")
    resp = await client.get(web.screen["image"])
    assert resp.status == 200 and resp.content_type in ("image/jpeg", "image/png")
    assert world.storage.user("tg", 7)["name"] == "Аня"
    assert app.online(7)


async def test_bad_signature_closes_with_auth_error(env):
    world, app, client, connect = env
    web = await connect()
    await web.send({"type": "hello", "initData": make_init_data(token="1:other", auth_date=int(world.time.now))})
    await web.wait(lambda: web.errors, "ошибка")
    assert web.errors[0]["code"] == "auth"
    await web.wait(lambda: web.ws.closed, "закрытие")


async def test_dev_user_only_in_dev_mode(env):
    world, app, client, connect = env
    web = await connect(dev_user={"id": 5, "name": "Dev"})
    assert "Выберите игру" in web.screen["text"]
    app.dev = False
    other = await connect()
    await other.send({"type": "hello", "dev_user": {"id": 6, "name": "Hacker"}})
    await other.wait(lambda: other.errors, "ошибка")
    assert other.errors[0]["code"] == "auth"


async def test_bad_frames_answered_but_connection_kept(env):
    world, app, client, connect = env
    web = await connect()
    await web.ws.send_str("не json")
    await web.wait(lambda: web.errors, "ошибка")
    assert web.errors[-1]["code"] == "bad_request"
    await web.send({"type": "press", "payload": "menu", "seq": 1})        # до hello
    await web.wait(lambda: len(web.errors) == 2, "вторая ошибка")
    await web.hello(dev_user={"id": 5, "name": "Dev"})
    await web.send({"type": "press", "payload": "x" * 300, "seq": 2})
    await web.wait(lambda: len(web.errors) == 3, "третья ошибка")
    web.seq = 2
    frame = await web.press("menu")
    assert frame["seq"] == 3 and "Выберите игру" in web.screen["text"]


async def test_memo_through_view_actions(env):
    world, app, client, connect = env
    web = await connect(dev_user={"id": 5, "name": "Dev"})
    frame = await web.press("new:memo")
    assert frame["seq"] == 1 and web.view["kind"] == "memo"
    assert web.view["pairs"]["found"] == 0 and {c["k"] for row in web.view["grid"]["cells"] for c in row} == {"back"}
    hint = (await client.get("/dev/hint", params={"user": "5"}))
    payload = (await hint.json())["payload"]
    assert payload.startswith("t:")
    await web.press(payload)
    assert any(c["k"] == "face" for row in web.view["grid"]["cells"] for c in row)
    await web.press(web.action("quit"))
    assert web.view is None and "Партия окончена" in web.screen["text"]


async def test_matrix_phases_come_as_pushes(env):
    world, app, client, connect = env
    web = await connect(dev_user={"id": 5, "name": "Dev"})
    await web.press("new:matrix")
    assert web.view["phase"] == "countdown" and web.view["timer"]["left"] == 60
    pushes = sum(1 for f in web.frames if f.get("seq") is None)
    await world.time.advance(3.5)            # отсчёт 2 с и показ 1 с
    await web.wait(lambda: web.view["phase"] == "input", "фаза ввода")
    assert sum(1 for f in web.frames if f.get("seq") is None) > pushes
    assert all(f["seq"] is None for f in web.frames[-3:] if f["type"] == "screen")


async def test_closed_window_does_not_break_timers(env):
    world, app, client, connect = env
    web = await connect(dev_user={"id": 5, "name": "Dev"})
    await web.press("new:matrix")
    await web.ws.close()
    await asyncio.sleep(0.05)
    assert not app.online(5)
    await world.time.advance(70)             # таймеры доходят до конца партии в пустоту
    again = await connect(dev_user={"id": 5, "name": "Dev"})
    assert "Выберите игру" in again.screen["text"]


async def test_friend_game_between_mini_app_and_chat(env):
    """Хозяин в Mini App, гость — в чате с ботом; партия у хозяина обновляется на месте, сдача гостя —
    победа хозяина и карточка-уведомление в Mini App."""
    world, app, client, connect = env
    host = await connect(dev_user={"id": 5, "name": "Хозяин"})
    for payload in ("mp", "mpn:0", "mpn:0:reduced", "mpn:0:reduced:auto"):
        await host.press(payload)
    assert host.view["status"] == "waiting"
    code = host.view["invite"]["code"]
    guest = world.chat(77, "Гость")
    await guest.start(f"mp_{code}")
    assert "Вы против" in guest.text
    await host.wait(lambda: host.view and host.view["status"] == "active", "партия у хозяина")
    assert host.view["turn"] == "me" and host.view["opponent"]["name"] == "Гость"
    game = mp_game(guest)
    r, c = next((r, c) for r in range(8) for c in range(7) if game.host.shots[r][c] == ".")
    await host.press(host.action("fire", r=r, c=c))
    assert host.view["turn"] == "them"
    await guest.click("Сдаться")
    await host.wait(lambda: host.view["result"] is not None, "итог у хозяина")
    assert host.view["result"]["won"] and host.view["result"]["reason"] == "surrender"
    await host.wait(lambda: host.notices, "карточка-уведомление")
    assert "победа" in host.notices[-1]["text"]


async def test_start_param_joins_friend_game(env):
    world, app, client, connect = env
    host = world.chat(77, "Хозяин")
    await host.send()
    for label in ("Морской бой", "Играть с другом", "Без ограничений", "Малый", "Автоматическая"):
        await host.click(label)
    code = mp_game(host).code
    web = await connect(dev_user={"id": 5, "name": "Гость"}, start=f"mp_{code}")
    assert web.view["kind"] == "sea" and web.view["status"] == "active" and web.view["turn"] == "them"


async def test_ai_game_and_oriented_placement_in_mini_app(env):
    world, app, client, connect = env
    web = await connect(dev_user={"id": 5, "name": "Dev"})
    await web.press("ain:normal:0:reduced:manual")
    p = web.view["placement"]
    assert web.view["status"] == "placing" and p["sizes"] == [3, 2, 2, 1, 1, 1]
    frame = await web.press(web.action("place", r=3, c=6, o="h"))      # горизонтально у края — нельзя
    assert frame["note"] and "границ" in frame["note"]
    await web.press(web.action("place", r=3, c=6, o="v"))
    assert web.view["placement"]["current"] == [[2, 6], [3, 6], [4, 6]]
    await web.press(web.action("fix"))
    assert len(web.view["placement"]["fixed"]) == 1


async def test_image_cache_is_bounded(env):
    world, app, client, connect = env
    from games_core.ui import Screen
    for i in range(webapp.IMAGES_KEPT + 5):
        app.serialize(Screen("x", image=b"\x89PNG" + str(i).encode()))
    assert len(app.images) == webapp.IMAGES_KEPT
    assert (await client.get("/img/0000.png")).status == 404


async def test_dbg_notify_comes_as_notice_cards(env):
    """e2e фронтенда проверяет карточки так: админ шлёт dbg:notify — бот сам пишет игроку."""
    world, app, client, connect = env
    world.mgr.debug_users = frozenset({5})
    web = await connect(dev_user={"id": 5, "name": "Dev"})
    await web.press("dbg:notify")
    await web.wait(lambda: len(web.notices) >= 2, "карточки")
    assert all(n["rows"] for n in web.notices)
