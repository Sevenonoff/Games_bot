"""Связка игр ядра с aiogram (sea_fight_aiogram/games_tg.py) на фейковом Bot.

Нужен aiogram — его нет в .venv (несовместим с maxapi), поэтому прогон из venv бота:
    sea_fight_aiogram/.venv/bin/python -m pytest tests/test_tg_glue.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("aiogram")

from aiogram import types  # noqa: E402
from aiogram.exceptions import TelegramBadRequest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sea_fight_aiogram"))
import games_tg  # noqa: E402
from games_core.storage import Storage  # noqa: E402
from games_core.ui import Button, Reply, Screen  # noqa: E402

CHAT = 500
SCREEN = Screen("<b>Мемо</b>", [[Button("🂠", "t:abc123:0:0"), Button("🏠 Меню", "menu")]])


class FakeBot:
    def __init__(self):
        self.sent, self.edits = [], []
        self.edit_error = None
        self._ids = iter(range(100, 1000))

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self.sent.append((chat_id, text, reply_markup))
        return SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=next(self._ids))

    async def edit_message_text(self, text, chat_id, message_id, reply_markup=None, parse_mode=None):
        if self.edit_error:
            raise self.edit_error
        self.edits.append((chat_id, message_id, text, reply_markup))


def bad_request(text):
    return TelegramBadRequest(method=None, message=f"Bad Request: {text}")


@pytest.fixture
def calls(monkeypatch):
    """Перехват Message.edit_text и CallbackQuery.answer — в aiogram им нужен настоящий Bot."""
    log = {"edits": [], "answers": [], "edit_error": None}

    async def edit_text(self, text, reply_markup=None, parse_mode=None, **kw):
        if log["edit_error"]:
            raise log["edit_error"]
        log["edits"].append((self.message_id, text, reply_markup))

    async def answer(self, text=None, **kw):
        log["answers"].append(text)

    monkeypatch.setattr(types.Message, "edit_text", edit_text)
    monkeypatch.setattr(types.CallbackQuery, "answer", answer)
    return log


def callback(photo=None):
    user = types.User.model_construct(id=7, is_bot=False, first_name="Аня", username=None)
    message = types.Message.model_construct(message_id=55, chat=types.Chat.model_construct(id=CHAT, type="private"),
                                            photo=photo, date=0)
    return types.CallbackQuery.model_construct(id="1", from_user=user, message=message,
                                               chat_instance="x", data="g:menu")


def test_render_maps_payloads():
    markup = games_tg.render(SCREEN)
    assert [[b.callback_data for b in row] for row in markup.inline_keyboard] == [["g:t:abc123:0:0", "g:menu"]]
    assert games_tg.render(Screen("без кнопок")) is None


async def test_tap_edits_message_then_answers_note(calls):
    respond = games_tg.callback_responder(FakeBot(), callback(), {})
    ref = await respond(Reply(SCREEN, "Пара!"))
    assert ref == (CHAT, 55)
    assert calls["edits"][0][:2] == (55, SCREEN.text)
    assert calls["answers"] == ["Пара!"]


async def test_note_only_does_not_touch_message(calls):
    respond = games_tg.callback_responder(FakeBot(), callback(), {})
    assert await respond(Reply(note="Устарело")) is None
    assert calls["edits"] == [] and calls["answers"] == ["Устарело"]


async def test_not_modified_is_not_an_error(calls):
    calls["edit_error"] = bad_request("message is not modified")
    ref = await games_tg.callback_responder(FakeBot(), callback(), {})(Reply(SCREEN))
    assert ref == (CHAT, 55)


async def test_photo_message_gets_new_text_message(calls):
    bot = FakeBot()
    photo = [types.PhotoSize.model_construct(file_id="f", file_unique_id="u", width=1, height=1)]
    ref = await games_tg.callback_responder(bot, callback(photo), {})(Reply(SCREEN))
    assert calls["edits"] == []
    assert bot.sent[0][:2] == (CHAT, SCREEN.text)
    assert ref == (CHAT, 100)


async def test_push_edits_by_ref_and_ignores_not_modified():
    bot = FakeBot()
    mgr = games_tg.build_manager(bot, Storage(":memory:"), "games_bot")
    await mgr.push((CHAT, 55), SCREEN)
    assert bot.edits[0][:3] == (CHAT, 55, SCREEN.text)
    bot.edit_error = bad_request("message is not modified")
    await mgr.push((CHAT, 55), SCREEN)
    bot.edit_error = bad_request("message to edit not found")
    with pytest.raises(TelegramBadRequest):
        await mgr.push((CHAT, 55), SCREEN)


async def test_start_sends_menu_as_new_message():
    bot = FakeBot()
    mgr = games_tg.build_manager(bot, Storage(":memory:"), "games_bot")
    player = games_tg.make_player(7, "@anya", "Аня", CHAT)
    assert player.name == "anya" and player.platform == "tg"
    await games_tg.safe_handle(mgr, player, "menu", games_tg.new_message_sender(bot, CHAT))
    chat_id, text, markup = bot.sent[0]
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["g:new:memo", "g:new:matrix", "g:new:tower", "g:sea", "g:rec"]


async def test_invite_link_and_opponent_message():
    """Бой с другом: ссылка t.me с кодом; подключение друга присылает хозяину новое сообщение."""
    bot = FakeBot()
    mgr = games_tg.build_manager(bot, Storage(":memory:"), "games_bot")
    host = games_tg.make_player(7, "anya", "Аня", CHAT)
    guest = games_tg.make_player(8, "bob", "Боб", 600)
    await mgr.handle(host, "mpn:0:reduced:auto", games_tg.new_message_sender(bot, CHAT))
    invite = bot.sent[-1][1]
    code = next(iter(mgr.mp.games))
    assert f"https://t.me/games_bot?start=mp_{code}" in invite
    await mgr.handle(guest, games_tg.start_payload(f"mp_{code}"), games_tg.new_message_sender(bot, 600))
    assert bot.sent[-2][0] == 600 and "Вы против" in bot.sent[-2][1]      # гостю — партия
    assert bot.sent[-1][0] == CHAT and "Ваш ход" in bot.sent[-1][1]       # хозяину — новое сообщение
    await mgr.shutdown()
