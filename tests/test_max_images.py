"""Картинки в транспорте Max: загрузка один раз, повтор при устаревшем токене, без картинки — если никак."""
import asyncio

import pytest

pytest.importorskip("maxapi")

from max_bot import main  # noqa: E402
from games_core.ui import Button, Screen  # noqa: E402

PNG = b"\x89PNG fake"
SCREEN = Screen("меню", [[Button("Мемо", "new:memo")]], image=PNG)


class FakeBot:
    def __init__(self):
        self.uploads = 0

    async def upload_media(self, media):
        self.uploads += 1
        return f"upload-{self.uploads}"


@pytest.fixture(autouse=True)
def fresh_images(monkeypatch):
    monkeypatch.setattr(main, "IMAGES", main.Images())


def run(coro):
    return asyncio.run(coro)


def test_image_uploaded_once_and_put_before_keyboard():
    bot, calls = FakeBot(), []

    async def call(atts):
        calls.append(atts)
        return "ok"
    run(main.with_image_retry(bot, SCREEN, call))
    run(main.with_image_retry(bot, SCREEN, call))
    assert bot.uploads == 1
    assert calls[0][0] == "upload-1" and len(calls[0]) == 2


def test_stale_token_is_uploaded_again():
    bot, calls = FakeBot(), []

    async def call(atts):
        calls.append(atts)
        if atts[0] == "upload-1":
            raise RuntimeError("token expired")
        return "ok"
    assert run(main.with_image_retry(bot, SCREEN, call)) == "ok"
    assert bot.uploads == 2 and calls[-1][0] == "upload-2"


def test_screen_goes_without_image_if_it_keeps_failing():
    bot, calls = FakeBot(), []

    async def call(atts):
        calls.append(atts)
        if any(isinstance(a, str) for a in atts):
            raise RuntimeError("image rejected")
        return "ok"
    assert run(main.with_image_retry(bot, SCREEN, call)) == "ok"
    assert len(calls[-1]) == 1          # только клавиатура


def test_text_screen_errors_are_not_swallowed():
    async def call(atts):
        raise RuntimeError("network")
    with pytest.raises(RuntimeError):
        run(main.with_image_retry(FakeBot(), Screen("игра", [[Button("x", "menu")]]), call))
