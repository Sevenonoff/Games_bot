"""Разбор и прогон текстовых сценариев (сам механизм, не игры)."""
from pathlib import Path

import pytest

from tests.scenario import ScenarioFailed, parse, run

PATH = Path("x.scenario")


def one(text: str):
    [sc] = parse(text, PATH)
    return sc


def test_parse_steps_players_admins_and_draft():
    sc = one("""
        # комментарий
        @черновик
        Сценарий: Пример
          Админ: Алиса, Боб
          пишу /start
          [Алиса] жму «Морской бой»
          жму клетку 2, 3
          хожу верно 3 раза
          хожу верно до "Партия окончена"
          жду 1,5 с
          кнопки: Мемо | Рекорды
    """)
    assert sc.name == "Пример" and sc.draft and sc.error is None
    assert sc.admins == {"Алиса", "Боб"}
    assert [(s.player, s.action, s.args) for s in sc.steps] == [
        ("Тестер", "send", ("/start",)),
        ("Алиса", "click", ("«Морской бой»",)),
        ("Тестер", "tap", ("2", "3")),
        ("Тестер", "right", ("3",)),
        ("Тестер", "right_until", ('"Партия окончена"',)),
        ("Тестер", "wait", ("1,5",)),
        ("Тестер", "buttons", ("Мемо | Рекорды",)),
    ]
    assert sc.players == ["Тестер", "Алиса", "Боб"]


@pytest.mark.parametrize("text, error", [
    ("Сценарий: А\n  прыгаю", "строка 2: не понимаю шаг «прыгаю»"),
    ("пишу /start", "шаг вне сценария"),
    ("@срочно\nСценарий: А\n  пишу /start", "неизвестная метка @срочно"),
    ("Сценарий: А", "в сценарии нет шагов"),
])
async def test_syntax_errors_reported_on_run(text, error):
    sc = parse(text, PATH)[0]
    assert error in sc.error
    with pytest.raises(ScenarioFailed, match=error):
        await run(sc)


async def test_failure_shows_place_screen_and_transcript():
    sc = one("""
        Сценарий: Ждём не то
          пишу /start
          жму Морской бой
          вижу "Шахматы"
    """)
    with pytest.raises(ScenarioFailed) as e:
        await run(sc)
    msg = str(e.value)
    assert "x.scenario:5 — «Ждём не то»" in msg
    assert "ошибка: на экране нет «Шахматы»" in msg
    assert "[🤖 Играть с компьютером]" in msg          # экран игрока
    assert "4  [Тестер] жму Морской бой" in msg           # переписка


async def test_missing_button_lists_what_is_on_screen():
    sc = one("Сценарий: А\n  пишу /start\n  жму Шахматы")
    with pytest.raises(ScenarioFailed, match="кнопка 'Шахматы': найдено 0"):
        await run(sc)


async def test_transcript_collected():
    sc = one("Сценарий: А\n  пишу /start\n  вижу Выберите игру")
    transcript = []
    await run(sc, transcript)
    assert len(transcript) == 1 and "Выберите игру" in transcript[0]
