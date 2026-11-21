"""Сценарии «как в мессенджере»: нажатия по подписям кнопок, время виртуальное."""
import pytest

from games_core.texts import t
from games_core import seafight_mp as mp
from tests.harness import World, mp_game, mp_right_move, mp_targets, wait_ai, wait_preview, win_round, wrong_move


@pytest.fixture
async def world():
    w = World()
    yield w
    await w.close()
    assert not w.errors, w.errors


async def start_ai(chat, level="Обычный", ship_set="Малый", limit="Без ограничений", mode="Автоматическая"):
    await chat.send()
    await chat.click("Морской бой")
    await chat.click("Играть с компьютером")
    await chat.click(level)
    await chat.click(limit)
    await chat.click(ship_set)
    await chat.click(mode)
    return mp_game(chat)


async def test_ai_game_win_then_records(world):
    chat = world.chat()
    game = await start_ai(chat)
    assert game.vs_ai and game.ai_level == "normal" and game.turn == chat.player.user_id
    while game.status == mp.ACTIVE:
        await wait_ai(world, chat)
        cell = mp_right_move(chat)
        if cell is not None:
            await chat.tap(*cell)
    await wait_ai(world, chat)
    assert game.winner == chat.player.user_id and "Победа" in chat.text
    assert world.storage.ai_results_of("max", 42) == {"normal": (1, 0)}
    assert [p.game for p in world.storage.partias("max", 42)] == ["ai_reduced"]

    await chat.click("Меню")
    await chat.click("Рекорды")
    await chat.click("С компьютером (обычный)")
    assert "Тестер — <b>1</b> победа из 1" in chat.text and "← вы" in chat.text
    await chat.click("Играть с компьютером")
    assert "Время на ход" in chat.text           # сложность уже выбрана — дальше по мастеру


async def test_ai_wins_when_player_only_misses(world):
    """Игрок всё время мажет — компьютер топит его корабли и побеждает; поражение записано."""
    chat = world.chat()
    game = await start_ai(chat, level="Продвинутый")
    uid = chat.player.user_id
    for _ in range(200):
        if game.status != mp.ACTIVE:
            break
        await wait_ai(world, chat)
        if game.status == mp.ACTIVE and game.turn == uid:
            await chat.tap(*mp_targets(game, uid, ships=False)[0])
    await wait_ai(world, chat)
    assert game.winner == mp.AI_USER_ID and game.end_reason == mp.END_SUNK
    assert "Поражение" in chat.text
    assert world.storage.ai_results_of("max", uid) == {"advanced": (0, 1)}
    # компьютер ни разу не стрелял дважды в одну клетку
    ai_moves = [(m["r"], m["c"]) for m in game.moves if m["by"] == mp.AI_USER_ID]
    assert len(ai_moves) == len(set(ai_moves))


async def test_old_solo_sea_buttons_lead_to_sea_menu(world):
    chat = world.chat()
    await chat.send()
    await chat.press("new:sea_reduced")
    assert t("sea_choose").split("\n")[0] in chat.text
    assert chat.session is None


async def test_matrix_minute_passes_on_virtual_time(world):
    chat = world.chat()
    await chat.send()
    await chat.click("Матрица")
    assert t("phase_countdown", n=3) in chat.text and "⏱ 60 с" in chat.text
    await chat.tap(0, 0)
    assert chat.note == t("note_countdown")

    await world.time.advance(2.0)        # «2», «1», показ — правками сообщения
    assert t("phase_preview") in chat.text and world.messenger.pushes == 3
    await chat.tap(0, 0)
    assert chat.note == t("note_preview")

    await world.time.advance(1.0)        # таймер скрыл фигуры
    assert t("phase_matrix") in chat.text and "⏱ 60 с" in chat.text
    assert await win_round(world, chat) == t("note_round_ok")

    await wait_preview(world, chat)      # отсчёт и показ время партии не тратят
    assert "⏱ 60 с" in chat.text
    await world.time.advance(12.0)       # таймер обновляется сам, без нажатий
    assert "⏱ 50 с" in chat.text
    await world.time.advance(17.0)
    await chat.tap(*wrong_move(chat.session))
    assert chat.note == t("note_round_fail") and "⏱ 31 с" in chat.text

    await wait_preview(world, chat)
    await world.time.advance(31.0)       # конец минуты тоже приходит правкой, но раунд доигрывается
    assert t("timer_overtime") in chat.text and "Партия окончена" not in chat.text
    assert await win_round(world, chat) == t("note_round_ok")
    assert t("phase_done") in chat.text  # итог раунда, затем конец партии
    await world.time.advance(2.0)
    assert "Партия окончена" in chat.text and "Раундов пройдено: 2 из 3" in chat.text
    assert world.storage.top("max", "matrix")[0][:2] == (42, "Тестер")


async def test_tower_level_up_after_three_rounds(world):
    chat = world.chat()
    await chat.send()
    await chat.click("Поездка")
    assert await win_round(world, chat) == t("note_round_ok")
    assert await win_round(world, chat) == t("note_round_ok")
    assert await win_round(world, chat) == t("note_level_up", level=2)
    assert "уровень 2" in chat.text


async def test_matrix_level_down_after_two_errors(world):
    world.mgr.debug_users = frozenset({42})
    chat = world.chat()
    await chat.send("dbg:level:matrix:3")
    await chat.click("Играть")
    for note in (t("note_round_fail"), t("note_level_down", level=2)):
        await wait_preview(world, chat)
        await chat.tap(*wrong_move(chat.session))
        assert chat.note == note


async def test_text_message_interrupts_partia_and_old_buttons_go_stale(world):
    chat = world.chat()
    await chat.send()
    await chat.click("Мемо")
    old_cell = chat.cell(0, 0).data
    await chat.send()                   # любое сообщение — новое меню, партия прервана
    assert chat.session is None
    await chat.press(old_cell)
    assert chat.note == t("note_stale")
    assert world.storage.load_progress("max", 42, "memo").fail_count == 1


async def test_two_players_do_not_mix(world):
    alice, bob = world.chat(1, "Алиса"), world.chat(2, "Боб")
    for chat in (alice, bob):
        await chat.send()
        await chat.click("Мемо")
    assert alice.session is not bob.session
    while "Партия окончена" not in alice.text or "Партия окончена" not in bob.text:
        for chat in (alice, bob):
            if "Партия окончена" not in chat.text:
                await wait_preview(world, chat)
                if "Партия окончена" not in chat.text:
                    await chat.play_right()
    assert {name for _, name, _ in world.storage.top("max", "memo")} == {"Алиса", "Боб"}


async def test_tower_colors_and_inactive_cells(world):
    """Пустые клетки жёлтые всегда, клетки с числами белые; нажатие по пустой — не ошибка."""
    chat = world.chat()
    await chat.send()
    await chat.click("Поездка")
    s = chat.session
    empty = next((r, c) for r in range(s.round.rows) for c in range(s.round.cols)
                 if (r, c) not in s.round.cells)
    numbered = next(iter(s.round.cells))

    await world.time.advance(2.0)                     # показ
    assert chat.cell(*empty).text == "🟨"
    assert chat.cell(*numbered).text == str(s.round.cells[numbered])
    await world.time.advance(1.0)                     # ввод
    assert chat.cell(*empty).text == "🟨" and chat.cell(*numbered).text == "⬜"

    await chat.tap(*empty)
    assert chat.note is None and s.progress.fail_count == 0 and s.round.opened == 0
    await chat.play_right()
    first = min(s.round.cells, key=s.round.cells.get)
    assert chat.cell(*first).text == str(s.round.numbers[0])


async def test_abandoned_ai_game_does_not_block_notices(world):
    """Брошенный бой с компьютером без лимита времени ждёт вечно — но напоминаниям через полчаса не мешает."""
    chat = world.chat()
    await start_ai(chat)
    assert world.mgr.busy(chat.player.user_id)
    await world.time.advance(31 * 60)
    assert not world.mgr.busy(chat.player.user_id)
    await chat.press("mpb")                          # вернулся — партия на месте, его ход
    assert t("mp_your_turn") in chat.text
