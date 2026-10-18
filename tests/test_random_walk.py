"""Случайный обход: тысячи нажатий подряд, после каждого — проверка инвариантов.

Обходчик жмёт случайные кнопки текущего экрана, пишет боту текстом и проматывает
время. В партии он с вероятностью её «мастерства» делает верный ход — так обход
доходит до побед и новых уровней. Два игрока, один из них — админ с доступом к /dbg.
Упавший прогон воспроизводится по seed: в сообщении — последние действия.
"""
import random
from collections import deque

import pytest

from games_core.sessions import GAMES
from games_core.texts import t
from tests.harness import World, check_screen, live, right_move

STEPS = 2500
ADMIN = 1
SEA = ("sea_full", "sea_reduced")


def user_scores(world, uid: int) -> int:
    return world.storage.conn.execute(
        "SELECT COUNT(*) FROM scores WHERE user_id = ?", (uid,)).fetchone()[0]


async def step(rng, world, chats, log, skill) -> None:
    chat = rng.choice(chats)
    roll = rng.random()
    if roll < 0.05 or chat.ref is None:
        payload = "dbg" if chat.player.user_id == ADMIN and rng.random() < 0.5 else "menu"
        log.append(f"{chat.player.user_id} пишет {payload!r}")
        await chat.send(payload)
        return
    if roll < 0.20:
        seconds = rng.choice([0.3, 1.0, 5.0, 20.0, 61.0])
        log.append(f"время +{seconds}")
        await world.time.advance(seconds)
        return
    s = live(chat)
    cell = right_move(s)
    if s is not None and s.sid not in skill:
        skill[s.sid] = rng.choice([0.2, 0.6, 0.97])    # партии бывают и удачные, и не очень
    if cell is None or rng.random() > skill[s.sid]:
        cell = None
    button = chat.cell(*cell) if cell else rng.choice(chat.buttons)
    log.append(f"{chat.player.user_id} жмёт {button.text!r} ({button.data})")
    await chat.press(button.data)
    assert chat.note != t("note_stale"), "кнопка текущего экрана оказалась устаревшей"


@pytest.mark.parametrize("seed", range(6))
async def test_random_walk(seed):
    rng = random.Random(seed)
    world = World(seed=seed, debug_users={ADMIN})
    chats = [world.chat(ADMIN, "Админ"), world.chat(2, "Игрок")]
    log = deque(maxlen=25)
    finished_games, max_level, skill = set(), 1, {}
    try:
        for i in range(STEPS):
            before = {c.player.user_id: (live(c), user_scores(world, c.player.user_id)) for c in chats}
            await step(rng, world, chats, log, skill)
            assert not world.errors, world.errors
            for c in chats:
                uid = c.player.user_id
                s, scores = before[uid]
                if c.ref is not None:
                    check_screen(c)
                if log[-1].endswith("(dbg:reset)") and log[-1].startswith(f"{uid} "):
                    continue
                if s is not None and c.session is not s:
                    assert s.finished, "прерванная партия не закрыта"
                done = s is not None and s.finished
                recorded = done and (s.game not in SEA or s.board.is_won())
                assert user_scores(world, uid) - scores == int(recorded), \
                    f"игрок {uid}: результат {'не ' if recorded else ''}записан ({s and s.game})"
                if done:
                    finished_games.add(s.game)
                    max_level = max(max_level, s.progress.level)
                    if c.session is s:      # закончилась сама или кнопкой, а не прервана
                        assert "Партия окончена" in c.text, "партия закончилась, а экран не обновился"
    except AssertionError as e:
        raise AssertionError(f"seed={seed}, шаг {i}: {e}\nпоследние действия:\n" + "\n".join(log)) from e
    finally:
        await world.close()
    # обход не застрял в одном месте
    assert finished_games == set(GAMES), finished_games
    assert max_level > 1
