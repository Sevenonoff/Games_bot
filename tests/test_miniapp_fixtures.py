"""Образцы экранов Mini App (docs/miniapp/fixtures/*.json): по ним фронтенд верстается без сервера.

Партии идут на виртуальном времени с фиксированным seed. Каждый образец — кадр «screen», как его
шлёт сервер: {"text", "rows", "image", "view"}. Тест сверяет образцы с кодом; если схема view
поменялась — обновить их тем же коммитом:
    UPDATE_FIXTURES=1 .venv/bin/python -m pytest tests/test_miniapp_fixtures.py
"""
import json
import os
import re
from pathlib import Path

from games_core import seafight_mp as mp
from games_core import seafight_solo as sea
from games_core.sessions import SEA_SYMBOLS
from sea_fight_aiogram.webapp import WebApp
from tests.harness import World, mp_game, mp_targets, wait_ai, wait_preview, wrong_moves

FIXTURES = Path(__file__).resolve().parent.parent / "docs" / "miniapp" / "fixtures"
SID = "a1b2c3"


def frame(app: WebApp, screen, sid=None) -> dict:
    data = app.serialize(screen)
    if data["image"]:
        data["image"] = "/img/example.jpg"
    text = json.dumps(data, ensure_ascii=False, indent=1)
    if sid:
        text = text.replace(sid, SID)       # номер партии случайный — в образце постоянный
    return json.loads(text)


async def collect() -> dict:
    world = World(seed=3, platform="tg")
    app = WebApp(bot_token="", make_player=lambda u: None)
    out = {}
    chat = world.chat(1, "Тестер")

    def keep(name, screen=None):
        s = chat.session
        out[name] = frame(app, screen or chat.screen, s.sid if s else None)

    try:
        await chat.send()
        keep("menu")

        # мемо: одна карта, несовпавшая пара, собранное поле, итог
        await chat.click("Мемо")
        s = chat.session
        b = s.board
        await chat.tap(*divmod(0, b.cols))
        keep("memo-play")
        await chat.tap(*wrong_moves(s)[-1])
        keep("memo-mismatch")
        await world.time.advance(4)
        while not s.done:
            await chat.play_right()
        keep("memo-done")
        await chat.tap(0, 0)
        out["result-memo"] = frame(app, chat.screen)

        # матрица: отсчёт, показ, ввод, итог раунда, разбор ошибки
        await chat.send()
        await chat.click("Матрица")
        keep("matrix-countdown")
        await world.time.advance(2.05)
        keep("matrix-preview")
        await wait_preview(world, chat)
        await chat.play_right()
        keep("matrix-input")
        while chat.session.phase == "input":
            await chat.play_right()
        keep("matrix-done")
        await wait_preview(world, chat)
        await chat.tap(*wrong_moves(chat.session)[0])
        keep("matrix-review")

        # поездка на числах: ввод и разбор
        await chat.send()
        await chat.click("Поездка")
        await wait_preview(world, chat)
        await chat.play_right()
        keep("tower-input")
        await chat.tap(*wrong_moves(chat.session)[0])
        keep("tower-review")

        # проложи дорогу: показ, ввод вслепую, итог, разбор
        await chat.send()
        await chat.click("Проложи дорогу")
        await world.time.advance(2.05)
        keep("path-preview")
        await wait_preview(world, chat)
        await chat.play_right()
        keep("path-input")
        while chat.session.phase == "input":
            await chat.play_right()
        keep("path-done")
        await wait_preview(world, chat)
        await chat.tap(*min(chat.session.round.blocks))
        keep("path-review")

        # морской бой с компьютером: мастер, расстановка, ход, компьютер думает, мигание, итог
        await chat.send()
        await chat.click("Морской бой")
        keep("sea-menu")
        await chat.click("Играть с компьютером")
        keep("ai-level")
        await chat.press("ain:advanced:30:reduced:manual")
        keep("sea-placement")
        await chat.tap(0, 1)
        keep("sea-placement-current")
        game = mp_game(chat)
        await chat.click("Сдаться")
        await chat.press("ain:advanced:30:reduced:auto")
        keep("sea-my-turn")
        game = mp_game(chat)
        await chat.tap(*mp_targets(game, 1, ships=False)[0])
        keep("sea-ai-thinking")
        await wait_ai(world, chat)
        keep("sea-their-shot")
        ship = min(game.guest.ships, key=len)
        out["sea-blink"] = frame(app, world.mgr.mp.screen(game, game.host,
                                                          highlight=(1, set(ship), SEA_SYMBOLS[sea.SHOT_HIT])))
        while game.status == mp.ACTIVE:
            await wait_ai(world, chat)
            if game.status == mp.ACTIVE and game.turn == 1:
                await chat.tap(*mp_targets(game, 1, ships=True)[0])
        await wait_ai(world, chat)
        keep("sea-result")

        # бой с другом: приглашение
        await chat.send()
        for label in ("Морской бой", "Играть с другом", "1 мин", "Полный", "Автоматическая"):
            await chat.click(label)
        keep("sea-invite")
    finally:
        await world.close()
    return out


async def test_fixtures_match_code():
    fixtures = await collect()
    update = os.getenv("UPDATE_FIXTURES") == "1"
    if update:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        for old in FIXTURES.glob("*.json"):
            old.unlink()
    stale = []
    for name, data in fixtures.items():
        path = FIXTURES / f"{name}.json"
        text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
        if update:
            path.write_text(text, encoding="utf-8")
        elif not path.exists() or path.read_text(encoding="utf-8") != text:
            stale.append(name)
    assert not stale, f"образцы устарели: {stale} — UPDATE_FIXTURES=1 .venv/bin/python -m pytest {__file__}"
    if not update:
        extra = {p.stem for p in FIXTURES.glob("*.json")} - set(fixtures)
        assert not extra, f"лишние образцы: {extra}"


def test_fixture_states_cover_every_phase():
    """Образцы покрывают все фазы и статусы из tz-m1-core.md §3."""
    views = [json.loads(p.read_text(encoding="utf-8"))["view"] for p in FIXTURES.glob("*.json")]
    phases = {(v["kind"], v.get("phase") or v.get("status")) for v in views if v}
    for kind in ("matrix", "path"):
        for phase in ("countdown" if kind == "matrix" else "preview", "input", "done", "review"):
            assert (kind, phase) in phases, (kind, phase)
    assert {("sea", s) for s in ("placing", "active", "finished", "waiting")} <= phases
    assert any(v and v["kind"] == "sea" and v["blink"] for v in views)
    assert any(v and v["kind"] == "sea" and v["thinking"] for v in views)
    assert re.search(SID, (FIXTURES / "memo-play.json").read_text(encoding="utf-8"))
