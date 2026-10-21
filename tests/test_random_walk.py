"""Случайный обход: тысячи нажатий подряд, после каждого — проверка инвариантов.

Обходчик жмёт случайные кнопки текущего экрана, пишет боту текстом и проматывает
время. В партии он с вероятностью её «мастерства» делает верный ход — так обход
доходит до побед и новых уровней. Два игрока, один из них — админ с доступом к /dbg.
Упавший прогон воспроизводится по seed: в сообщении — последние действия.
"""
import random
from collections import Counter, deque

import pytest

from games_core import days, seafight_mp as mp
from games_core.sessions import GAMES
from games_core.ui import data
from games_core.texts import t
from tests.harness import World, check_screen, live, mp_game, mp_right_move, right_move

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
    if roll < 0.08 and world.invite_link():
        # друг переходит по последней ссылке-приглашению (своей — тоже бывает)
        param = world.invite_link()
        log.append(f"{chat.player.user_id} переходит по ссылке {param}")
        await chat.start(param)
        return
    if roll < 0.20:
        seconds = rng.choice([0.3, 1.0, 5.0, 20.0, 61.0, 200.0])
        log.append(f"время +{seconds}")
        await world.time.advance(seconds)
        return
    if roll < 0.204:
        # время суток уведомлений: полдень (от друзей), вечер (напоминания), ночь (тишина)
        hh = rng.choice([9, 12, 13, 19, 21, 23])
        log.append(f"наступает {hh}:00")
        await world.time.advance(days.next_time(world.time.now, hh, 0) - world.time.now)
        # прошли часы: старые партии закрыты по простою, игроки возвращаются в меню
        for c in chats:
            await c.send("menu")
        return
    if await mp_step(rng, chat, log):
        return
    s = live(chat)
    if s is not None and s.msg_ref != chat.ref:
        s = None       # партия в сообщении повыше, а жмём по последнему (там — бой с другом)
    cell = right_move(s)
    if s is not None and s.sid not in skill:
        skill[s.sid] = rng.choice([0.2, 0.6, 0.97])    # партии бывают и удачные, и не очень
    if cell is None or rng.random() > skill[s.sid]:
        cell = None
    button = chat.cell(*cell) if cell else rng.choice(chat.buttons)
    log.append(f"{chat.player.user_id} жмёт {button.text!r} ({button.data})")
    await chat.press(button.data)
    assert chat.note != t("note_stale"), "кнопка текущего экрана оказалась устаревшей"


# в TG — настройки Manager из sea_fight_aiogram/games_menu.py; кнопки морского боя TG ядру незнакомы
async def mp_step(rng, chat, log) -> bool:
    """Бой с другом идёт к развязке: вернуться к партии, расставить корабль, выстрелить в цель."""
    game = mp_game(chat)
    if game is None or game.status not in (mp.PLACING, mp.ACTIVE) or rng.random() > 0.7:
        return False
    uid = chat.player.user_id
    side = game.side(uid)
    on_screen = any(b.data.split(":")[0] in ("mpf", "mpp", "mpy", "mpg") for b in chat.buttons)
    if not on_screen:
        log.append(f"{uid} возвращается к партии")
        await chat.press("mpb")
        return True
    if game.status == mp.PLACING and not side.ready:
        p = side.placement
        if p.current_cells():
            payload = data("mpk", game.code)
        elif p.is_complete():
            payload = data("mpy", game.code)
        else:
            size = p.current_size
            spot = next(((r, c) for r in range(p.rows) for c in range(p.cols - size + 1)
                         if p._check([(r, c + i) for i in range(size)]) is None), None)
            if spot is None:
                payload = data("mpz", game.code)
            else:
                payload = data("mpp", game.code, spot[0], spot[1] + (size - 1) // 2)
        log.append(f"{uid} расставляет: {payload}")
        await chat.press(payload)
        return True
    cell = mp_right_move(chat)
    if cell is not None:
        log.append(f"{uid} стреляет в {cell}")
        await chat.press(chat.mp_cell(*cell).data)
        return True
    return False


def check_notices(world) -> None:
    """Сообщения от бота сами по себе: не больше одного уведомления от друзей и одного
    напоминания в день; уведомления от друзей — только днём."""
    kinds = Counter()
    for chat_id, at, screen in world.sent_at:
        kind = ("friends" if screen.text.startswith(t("notify_friends", names="")[:10])
                else "reminder" if screen.text == t("notify_reminder") else None)
        if kind is None:
            continue
        kinds[chat_id, days.day_key(at), kind] += 1
        if kind == "friends":
            assert 12 <= days.hour(at) < 22, f"уведомление от друзей в {days.local(at):%H:%M}"
    extra = {k: n for k, n in kinds.items() if n > 1}
    assert not extra, f"повторные уведомления за день: {extra}"


def check_mp(world, mp_moves, rating_reset: bool) -> None:
    """Бой с другом: после конца партии ходов нет; рейтинг не берётся из ниоткуда; одна открытая партия на игрока."""
    for game in world.mgr.mp.games.values():
        if game.status == mp.FINISHED:
            assert mp_moves.setdefault(game.code, len(game.moves)) == len(game.moves), \
                f"ход после конца партии {game.code}"
    for state in world.storage.load_mp(world.platform, (mp.FINISHED,)):
        code, moves = state["code"], len(state["moves"])
        assert mp_moves.setdefault(code, moves) == moves, f"ход после конца партии {code}"
    rows = world.storage.conn.execute("SELECT game_type, SUM(rating - 1000) FROM ratings GROUP BY game_type").fetchall()
    assert rating_reset or all(total == 0 for _, total in rows), f"сумма рейтингов изменилась: {[tuple(r) for r in rows]}"
    for uid in world.chats:
        open_games = [g for g in world.mgr.mp.games.values() if g.status in mp.OPEN and g.side(uid)]
        assert len(open_games) <= 1, f"у игрока {uid} открыто партий: {len(open_games)}"


@pytest.mark.parametrize("seed, platform", [(s, "max") for s in range(6)] + [(s, "tg") for s in range(2)])
async def test_random_walk(seed, platform):
    rng = random.Random(seed)
    world = World(seed=seed, debug_users={ADMIN}, platform=platform)
    chats = [world.chat(ADMIN, "Админ"), world.chat(2, "Игрок")]
    log = deque(maxlen=25)
    finished_games, max_level, skill = set(), 1, {}
    mp_moves = {}          # код законченного боя → число ходов в момент окончания
    rating_reset = False   # /dbg reset стирает и рейтинг — сумма рейтингов после него не сходится
    try:
        for i in range(STEPS):
            before = {c.player.user_id: (live(c), user_scores(world, c.player.user_id)) for c in chats}
            await step(rng, world, chats, log, skill)
            assert not world.errors, world.errors
            rating_reset = rating_reset or log[-1].endswith("(dbg:reset)")
            check_mp(world, mp_moves, rating_reset)
            check_notices(world)
            for c in chats:
                uid = c.player.user_id
                s, scores = before[uid]
                if c.ref is not None:
                    check_screen(c)
                if log[-1].endswith("(dbg:reset)") and log[-1].startswith(f"{uid} "):
                    continue
                if log[-1].startswith("наступает"):
                    continue    # за часы простоя партия убрана без результата — так и задумано
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
