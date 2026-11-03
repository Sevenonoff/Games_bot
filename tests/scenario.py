"""Сценарии нажатий текстом: пишутся при проектировании фичи, прогоняются в тестах.

Формат и словарь шагов — tests/scenarios/README.md. Каждый сценарий идёт на
свежем боте (пустая БД, виртуальное время); после каждого шага, кроме ожиданий
сценария, проверяются общие инварианты экрана (harness.check_screen).

Посмотреть переписку с ботом по сценарию, даже если он проходит:
    .venv/bin/python -m tests.scenario tests/scenarios/sea.scenario
"""
import asyncio
import html
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from games_core import days, path
from games_core.ui import BLANK, Screen
from games_core.manager import text_payload
from games_core.sessions import PATH_EMPTY, TimedSession
from games_core import seafight_mp as mp
from tests.harness import (Chat, World, check_screen, live, mp_game, mp_right_move, mp_targets, path_detour,
                           path_middle_first, right_move, settle, wait_preview, win_round, wrong_moves)

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
DEFAULT_PLAYER = "Тестер"
DRAFT_TAG = "@черновик"
MAX_MOVES = 1000          # «хожу верно до …» — защита от бесконечного цикла


class ScenarioFailed(AssertionError):
    pass


@dataclass
class Step:
    line: int
    source: str
    player: str
    action: str
    args: Tuple[str, ...]


@dataclass
class Scenario:
    path: Path
    line: int
    name: str
    draft: bool = False
    admins: Set[str] = field(default_factory=set)
    platform: str = "max"
    steps: List[Step] = field(default_factory=list)
    error: Optional[str] = None       # ошибка разбора: покажем при запуске, а не при сборе тестов

    @property
    def id(self) -> str:
        return f"{self.path.stem}: {self.name}"

    @property
    def players(self) -> List[str]:
        names = [DEFAULT_PLAYER] + sorted(self.admins) + [s.player for s in self.steps]
        return list(dict.fromkeys(names))


# --- разбор ---

STEP_PATTERNS = [
    (r"пишу код приглашения", "send_code"),
    (r"пишу (.+)", "send"),
    (r"перехожу по ссылке", "follow_invite"),
    (r"стреляю мимо", "mp_miss"),
    (r"стреляю по кораблю", "mp_hit"),
    (r"доводим партию до последнего выстрела", "mp_endgame"),
    (r"расставляю корабли", "mp_place"),
    (r"перезапускаю бота", "restart"),
    (r"жму клетку (\d+)[ ,]+(\d+)", "tap"),
    (r"жму чёрную клетку", "tap_blank"),
    (r"жму клетку дороги ещё раз", "path_again"),
    (r"жму на (человека|дом)", "path_end"),
    (r"на поле видны человек и дом", "path_ends_shown"),
    (r"жму (.+)", "click"),
    (r"хожу верно до (.+)", "right_until"),
    (r"хожу верно(?: (\d+) раза?)?", "right"),
    (r"ошибаюсь", "wrong"),
    (r"выигрываю раунд", "win_round"),
    (r"доигрываю партию", "play_partia"),
    (r"жду (\d+(?:[.,]\d+)?) ?с(?:ек)?", "wait"),
    (r"в итоге не вижу (.+)", "result_not_see"),
    (r"в итоге вижу (.+)", "result_see"),
    (r"не вижу (.+)", "not_see"),
    (r"вижу (.+)", "see"),
    (r"без уведомления", "no_note"),
    (r"уведомление (.+)", "note"),
    (r"нет кнопки (.+)", "no_button"),
    (r"есть кнопка (.+)", "has_button"),
    (r"кнопки: (.+)", "buttons"),
    (r"открыто клеток:? (\d+)", "open_cells"),
    (r"на поле есть (.+)", "field_has"),
    (r"на поле нет (.+)", "field_lacks"),
    (r"иду кратчайшим путём", "path_shortest"),
    (r"иду в обход", "path_detour"),
    (r"кладу дорогу с середины", "path_middle"),
    (r"наступаю на препятствие", "path_block"),
    (r"числа поездки с разрывом", "trip_gap"),
    (r"наступает воскресенье (\d{1,2}):(\d{2})", "clock_sunday"),
    (r"наступает (\d{1,2}):(\d{2})", "clock"),
    (r"есть картинка", "has_image"),
    (r"нет картинки", "no_image"),
    (r"картинка пути: зона (\d+), шаг (\d+)(?: \((пройдена|облака расходятся)\))?", "journey_image"),
    (r"картинка — открытка (\d+) дн\S*", "card_image"),
    (r"приходит сообщение (.+)", "incoming"),
    (r"сообщений не приходило", "no_incoming"),
]


def unquote(text: str) -> str:
    text = text.strip()
    for left, right in (('"', '"'), ("«", "»")):
        if len(text) >= 2 and text.startswith(left) and text.endswith(right):
            return text[1:-1]
    return text


def parse_step(line_no: int, line: str) -> Optional[Step]:
    player = DEFAULT_PLAYER
    m = re.fullmatch(r"\[(.+?)\]\s*(.+)", line)
    if m:
        player, line = m[1].strip(), m[2]
    for pattern, action in STEP_PATTERNS:
        m = re.fullmatch(pattern, line, re.IGNORECASE)
        if m:
            return Step(line_no, line, player, action, tuple(g for g in m.groups() if g is not None))
    return None


def parse(text: str, path: Path) -> List[Scenario]:
    scenarios: List[Scenario] = []
    tags: Set[str] = set()
    current: Optional[Scenario] = None
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            tags.update(line.split())
            continue
        m = re.fullmatch(r"Сценарий:\s*(.+)", line)
        if m:
            current = Scenario(path, no, m[1].strip(), draft=DRAFT_TAG in tags)
            unknown = tags - {DRAFT_TAG}
            if unknown:
                current.error = f"строка {no}: неизвестная метка {', '.join(sorted(unknown))}"
            tags = set()
            scenarios.append(current)
            continue
        if current is None:
            current = Scenario(path, no, "(до первого «Сценарий:»)")
            current.error = f"строка {no}: шаг вне сценария — начните с «Сценарий: название»"
            scenarios.append(current)
            continue
        m = re.fullmatch(r"Платформа:\s*(max|tg)", line, re.IGNORECASE)
        if m:
            current.platform = m[1].lower()
            continue
        m = re.fullmatch(r"Админы?:\s*(.+)", line)
        if m:
            current.admins.update(n.strip() for n in m[1].split(","))
            continue
        step = parse_step(no, line)
        if step is None:
            current.error = current.error or (
                f"строка {no}: не понимаю шаг «{line}».\nИзвестные шаги — tests/scenarios/README.md")
        else:
            current.steps.append(step)
    for sc in scenarios:
        if not sc.steps and sc.error is None:
            sc.error = f"строка {sc.line}: в сценарии нет шагов"
    return scenarios


def load(paths) -> List[Scenario]:
    return [sc for path in paths for sc in parse(Path(path).read_text(encoding="utf-8"), Path(path))]


def load_all(directory: Path = SCENARIOS_DIR) -> List[Scenario]:
    return load(sorted(directory.glob("*.scenario")))


# --- шаги ---

def plain(text: str) -> str:
    """Текст экрана, как его видит человек: без HTML-разметки."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def labels(chat: Chat) -> List[str]:
    """Подписи кнопок, кроме клеток поля."""
    return [b.text for b in chat.buttons
            if b.data != "noop" and b.data.split(":")[0] not in ("t", "b", "mpf", "mpp")]


async def do_send(world: World, chat: Chat, text: str) -> None:
    await chat.send(text_payload(unquote(text)))


async def do_click(world: World, chat: Chat, label: str) -> None:
    await chat.click(unquote(label))


async def do_tap(world: World, chat: Chat, r: str, c: str) -> None:
    await chat.tap(int(r), int(c))


async def do_tap_blank(world: World, chat: Chat) -> None:
    blank = next((b for b in chat.buttons if b.data.startswith("b:")), None)
    assert blank is not None, "на экране нет чёрных клеток"
    assert blank.text == BLANK
    await chat.press(blank.data)


async def right_once(world: World, chat: Chat) -> None:
    if mp_game(chat) is not None:
        cell = mp_right_move(chat)
        assert cell is not None, "в бою с другом сейчас не ваш ход"
        await chat.tap(*cell)
        return
    await wait_preview(world, chat)
    cell = right_move(live(chat))
    assert cell is not None, "сейчас нет верного хода: партии нет или она окончена"
    await chat.tap(*cell)


async def do_right(world: World, chat: Chat, times: str = "1") -> None:
    for _ in range(int(times)):
        await right_once(world, chat)


def partia_screen(chat: Chat) -> Screen:
    """Сообщение последней партии: после итога бот может прислать ещё сообщение (открытку, новую зону)."""
    s = chat.session
    if s is not None and s.msg_ref in chat.messenger.screens:
        return chat.messenger.screens[s.msg_ref]
    return chat.screen


def _shown(chat: Chat, text: str) -> bool:
    return text in plain(chat.text) or text in plain(partia_screen(chat).text)


async def do_right_until(world: World, chat: Chat, text: str) -> None:
    text = unquote(text)
    for _ in range(MAX_MOVES):
        if _shown(chat, text):
            return
        if mp_game(chat) is None:
            # итог раунда или собранного поля проходит сам — текст может появиться и после него
            await wait_preview(world, chat)
            if _shown(chat, text):
                return
        await right_once(world, chat)
    raise AssertionError(f"за {MAX_MOVES} верных ходов «{text}» так и не появилось")


async def do_wrong(world: World, chat: Chat) -> None:
    await wait_preview(world, chat)
    s = live(chat)
    assert s is not None, "партии нет — ошибиться негде"
    for cell in wrong_moves(s):
        await chat.tap(*cell)


async def do_play_partia(world: World, chat: Chat) -> None:
    """Довести любую партию до записанного итога: матрица (по таймеру) — раунд и «Закончить»,
    остальные — верными ходами до конца."""
    s = live(chat)
    assert s is not None, "партии нет"
    if s.game == "matrix":
        await do_win_round(world, chat)
        await do_click(world, chat, "Закончить")
    await do_right_until(world, chat, "Партия окончена")


async def do_win_round(world: World, chat: Chat) -> None:
    assert isinstance(live(chat), TimedSession), "«выигрываю раунд» — только в играх с раундами"
    await win_round(world, chat)


async def do_wait(world: World, chat: Chat, seconds: str) -> None:
    await world.time.advance(float(seconds.replace(",", ".")))


async def do_see(world: World, chat: Chat, text: str) -> None:
    assert unquote(text) in plain(chat.text), f"на экране нет «{unquote(text)}»"


async def do_result_see(world: World, chat: Chat, text: str) -> None:
    shown = plain(partia_screen(chat).text)
    assert unquote(text) in shown, f"в итоге партии нет «{unquote(text)}»:\n{shown}"


async def do_result_not_see(world: World, chat: Chat, text: str) -> None:
    shown = plain(partia_screen(chat).text)
    assert unquote(text) not in shown, f"в итоге партии есть «{unquote(text)}», а не должно быть"


async def do_not_see(world: World, chat: Chat, text: str) -> None:
    assert unquote(text) not in plain(chat.text), f"на экране есть «{unquote(text)}», а не должно быть"


async def do_note(world: World, chat: Chat, text: str) -> None:
    assert chat.note is not None and unquote(text) in chat.note, \
        f"ждали уведомление «{unquote(text)}», было {chat.note!r}"


async def do_no_note(world: World, chat: Chat) -> None:
    assert chat.note is None, f"ждали нажатие без уведомления, было {chat.note!r}"


CLOSED_CELLS = ("⬜", "🟨", PATH_EMPTY)   # закрытая карта / клетка без числа / пустая клетка дороги


async def do_open_cells(world: World, chat: Chat, count: str) -> None:
    cells = [b.text for b in chat.buttons if b.data.startswith("t:")]
    opened = sum(1 for text in cells if text not in CLOSED_CELLS)
    assert opened == int(count), f"открыто клеток: {opened}, ожидалось {count}; поле {cells}"


def field_cells(chat: Chat) -> List[str]:
    return [b.text for b in chat.buttons if b.data[:2] in ("t:", "b:")]


async def do_field_has(world: World, chat: Chat, symbol: str) -> None:
    assert any(unquote(symbol) in x for x in field_cells(chat)), \
        f"на поле нет «{unquote(symbol)}»: {field_cells(chat)}"


async def do_field_lacks(world: World, chat: Chat, symbol: str) -> None:
    assert not any(unquote(symbol) in x for x in field_cells(chat)), \
        f"на поле есть «{unquote(symbol)}», а не должно быть"


async def do_has_button(world: World, chat: Chat, label: str) -> None:
    assert any(unquote(label) in x for x in labels(chat)), f"нет кнопки «{unquote(label)}»"


async def do_no_button(world: World, chat: Chat, label: str) -> None:
    assert not any(unquote(label) in x for x in labels(chat)), f"есть кнопка «{unquote(label)}», а не должно быть"


async def do_buttons(world: World, chat: Chat, spec: str) -> None:
    expected = [unquote(x) for x in spec.split("|")]
    actual = labels(chat)
    ok = len(expected) == len(actual) and all(e in a for e, a in zip(expected, actual))
    assert ok, f"кнопки не те:\n  ждали {expected}\n  на экране {actual}"


# --- бой с другом ---

async def do_follow_invite(world: World, chat: Chat) -> None:
    param = world.invite_link()
    assert param is not None, "ни на одном экране нет ссылки-приглашения"
    await chat.start(param)


async def do_send_code(world: World, chat: Chat) -> None:
    param = world.invite_link()
    assert param is not None, "ни на одном экране нет приглашения"
    await chat.send(text_payload(param[len("mp_"):]))


def _mp_game(chat: Chat) -> mp.MpGame:
    game = mp_game(chat)
    assert game is not None, "у игрока нет боя с другом"
    return game


async def do_mp_miss(world: World, chat: Chat) -> None:
    await chat.tap(*mp_targets(_mp_game(chat), chat.player.user_id, ships=False)[0])


async def do_mp_hit(world: World, chat: Chat) -> None:
    """Попасть, по возможности не потопив: в корабль, у которого останутся целые клетки."""
    game, uid = _mp_game(chat), chat.player.user_id
    targets = mp_targets(game, uid, ships=True)
    ships = game.opponent(uid).ships
    alive = {cell: sum(1 for x in next(s for s in ships if cell in s) if x in targets) for cell in targets}
    await chat.tap(*max(targets, key=lambda cell: alive[cell]))


async def do_mp_endgame(world: World, chat: Chat) -> None:
    """Оба по очереди топят корабли соперника, пока у каждого не останется одна клетка
    до победы; следующий ход — за этим игроком."""
    game = _mp_game(chat)
    for _ in range(MAX_MOVES):
        left = {s.user_id: len(mp_targets(game, s.user_id, ships=True)) for s in game.sides}
        if all(n == 1 for n in left.values()) and game.turn == chat.player.user_id:
            return
        shooter = world.chats[game.turn]
        await shooter.tap(*mp_targets(game, game.turn, ships=left[game.turn] > 1)[0])
    raise AssertionError("не удалось довести партию до последнего выстрела")


async def do_mp_place(world: World, chat: Chat) -> None:
    """Расставить оставшиеся корабли нажатиями: каждый — горизонтально, в первое подходящее место."""
    p = _mp_game(chat).side(chat.player.user_id).placement
    assert p is not None, "расстановки нет"
    if p.current_cells():
        await chat.click("Зафиксировать")
    while not p.is_complete():
        size = p.current_size
        spot = next(((r, c) for r in range(p.rows) for c in range(p.cols - size + 1)
                     if p._check([(r, c + i) for i in range(size)]) is None), None)
        assert spot is not None, f"корабль на {size} клеток уже не встаёт"
        r, c = spot
        await chat.tap(r, c + (size - 1) // 2)
        await chat.click("Зафиксировать")


async def do_restart(world: World, chat: Chat) -> None:
    await world.restart()


# --- Проложи дорогу ---

async def _path_round(world: World, chat: Chat) -> path.PathRound:
    await wait_preview(world, chat)
    s = live(chat)
    assert s is not None and s.game == "path", "сейчас не идёт «Проложи дорогу»"
    return s.round


async def _walk(chat: Chat, cells) -> None:
    for cell in cells:
        await chat.tap(*cell)


async def do_path_shortest(world: World, chat: Chat) -> None:
    rnd = await _path_round(world, chat)
    assert not rnd.road, "дорога уже начата"
    await _walk(chat, rnd.solution)


async def do_path_detour(world: World, chat: Chat) -> None:
    rnd = await _path_round(world, chat)
    assert not rnd.road, "дорога уже начата"
    route = path_detour(rnd)
    assert route is not None, "на этом поле нет дороги длиннее кратчайшей"
    await _walk(chat, route)


async def do_path_middle(world: World, chat: Chat) -> None:
    rnd = await _path_round(world, chat)
    assert not rnd.road, "дорога уже начата"
    await _walk(chat, path_middle_first(rnd))


async def do_path_again(world: World, chat: Chat) -> None:
    rnd = await _path_round(world, chat)
    assert rnd.road, "дорога ещё не начата"
    await chat.tap(*rnd.road[-1])


async def do_path_end(world: World, chat: Chat, which: str) -> None:
    rnd = await _path_round(world, chat)
    await chat.tap(*rnd.ends[0 if which == "человека" else 1])


async def do_path_ends_shown(world: World, chat: Chat) -> None:
    s = live(chat)
    assert s is not None and s.game == "path", "сейчас не идёт «Проложи дорогу»"
    for end, icon in zip(s.round.ends, s.round.icons):
        assert chat.cell(*end).text == icon, f"на клетке {end} «{chat.cell(*end).text}», а не {icon}"


async def do_path_block(world: World, chat: Chat) -> None:
    await chat.tap(*min((await _path_round(world, chat)).blocks))


# --- Поездка на числах ---

async def do_trip_gap(world: World, chat: Chat) -> None:
    s = live(chat)
    assert s is not None and s.game == "tower", "сейчас не идёт «Поездка на числах»"
    numbers = s.round.numbers
    assert any(b - a > 1 for a, b in zip(numbers, numbers[1:])), f"числа без разрыва: {numbers}"


# --- время суток и сообщения от бота ---

async def do_clock(world: World, chat: Chat, hh: str, mm: str) -> None:
    """Промотать время до ближайших hh:mm по Москве."""
    await world.time.advance(days.next_time(world.time.now, int(hh), int(mm)) - world.time.now)


async def do_clock_sunday(world: World, chat: Chat, hh: str, mm: str) -> None:
    """Промотать время до ближайшего воскресенья hh:mm по Москве."""
    at = days.next_time(world.time.now, int(hh), int(mm))
    while days.local(at).weekday() != 6:
        at = days.next_time(at, int(hh), int(mm))
    await world.time.advance(at - world.time.now)


# --- картинки пути ---

async def do_has_image(world: World, chat: Chat) -> None:
    assert chat.screen.image is not None, "у сообщения нет картинки"


async def do_no_image(world: World, chat: Chat) -> None:
    assert chat.screen.image is None, "у сообщения есть картинка, а не должно быть"


async def do_journey_image(world: World, chat: Chat, zone: str, step: str, mode: Optional[str] = None) -> None:
    from games_core import journey_art, motivation
    z, st = int(zone) - 1, int(step)
    kind = {None: "current", "пройдена": "done", "облака расходятся": "reveal"}[mode]
    expected = journey_art.render_zone(z, st, motivation.zone_size(z), kind)
    assert chat.screen.image == expected, f"на картинке не зона {zone}, шаг {step} ({kind})"


async def do_card_image(world: World, chat: Chat, n: str) -> None:
    from games_core import journey_art
    assert chat.screen.image == journey_art.render_card(int(n)), f"на картинке не открытка {n} дней"


def _new_messages(world: World, chat: Chat):
    inbox = world.inbox.get(chat.player.chat_id, [])
    new, chat.seen_sent = inbox[chat.seen_sent:], len(inbox)
    return new


async def do_incoming(world: World, chat: Chat, text: str) -> None:
    await settle()
    new = _new_messages(world, chat)
    text = unquote(text)
    assert any(text in plain(screen.text) for screen in new), \
        f"ждали сообщение от бота «{text}», пришло: {[plain(s.text) for s in new]}"


async def do_no_incoming(world: World, chat: Chat) -> None:
    await settle()
    new = _new_messages(world, chat)
    assert not new, f"ждали тишину, а бот прислал: {[plain(s.text) for s in new]}"


ACTIONS: Dict[str, Callable] = {
    "send_code": do_send_code, "follow_invite": do_follow_invite, "mp_miss": do_mp_miss,
    "mp_hit": do_mp_hit, "mp_endgame": do_mp_endgame, "mp_place": do_mp_place, "restart": do_restart,
    "send": do_send, "click": do_click, "tap": do_tap, "tap_blank": do_tap_blank,
    "right": do_right, "right_until": do_right_until, "wrong": do_wrong, "win_round": do_win_round, "play_partia": do_play_partia,
    "wait": do_wait, "see": do_see, "not_see": do_not_see, "note": do_note, "no_note": do_no_note,
    "has_button": do_has_button, "no_button": do_no_button, "buttons": do_buttons,
    "open_cells": do_open_cells, "field_has": do_field_has, "field_lacks": do_field_lacks,
    "path_shortest": do_path_shortest, "path_detour": do_path_detour, "path_middle": do_path_middle,
    "path_again": do_path_again, "path_end": do_path_end, "path_ends_shown": do_path_ends_shown, "path_block": do_path_block,
    "trip_gap": do_trip_gap,
    "clock": do_clock, "clock_sunday": do_clock_sunday, "incoming": do_incoming, "no_incoming": do_no_incoming,
    "result_see": do_result_see, "result_not_see": do_result_not_see, "has_image": do_has_image, "no_image": do_no_image, "journey_image": do_journey_image, "card_image": do_card_image,
}


# --- прогон ---

def describe(chat: Chat, with_field: bool = False) -> str:
    if chat.ref is None:
        return "(бот ещё ничего не прислал)"
    text = plain(chat.text).strip()
    out = text if text else "(пусто)"
    if with_field:
        for row in chat.screen.rows:
            if all(b.data[:2] in ("t:", "b:") for b in row):
                out += "\n" + " ".join(b.text for b in row)
    if labels(chat):
        out += "\n[" + "] [".join(labels(chat)) + "]"
    if chat.note:
        out += f"\n(уведомление: {chat.note})"
    return out


def indent(text: str, prefix: str = "      ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


async def run(sc: Scenario, transcript: Optional[List[str]] = None, verbose: bool = False) -> None:
    """Прогнать сценарий. При ошибке — ScenarioFailed с местом, экраном и ходом переписки."""
    if sc.error:
        raise ScenarioFailed(f"{sc.path.name}: {sc.error}")
    log = transcript if transcript is not None else []
    ids = {name: i for i, name in enumerate(sc.players, 1)}
    world = World(debug_users={ids[a] for a in sc.admins}, platform=sc.platform)
    chats = {name: world.chat(uid, name) for name, uid in ids.items()}
    step = None
    try:
        for step in sc.steps:
            chat = chats[step.player]
            await ACTIONS[step.action](world, chat, *step.args)
            assert not world.errors, f"ошибка в таймере: {world.errors!r}"
            for c in chats.values():
                if c.ref is not None:
                    check_screen(c)
            if step.action in ("send", "click", "tap", "tap_blank", "right", "right_until", "wrong", "win_round", "play_partia",
                               "wait", "send_code", "follow_invite", "mp_miss", "mp_hit", "mp_endgame", "mp_place",
                               "path_shortest", "path_detour", "path_middle", "path_again", "path_end", "path_block",
                               "clock", "incoming"):
                log.append(f"{step.line:>3}  [{step.player}] {step.source}\n"
                           f"{indent(describe(chat, with_field=verbose))}")
    except AssertionError as e:
        who = step.player if step else DEFAULT_PLAYER
        raise ScenarioFailed("\n".join([
            f"{sc.path.name}:{step.line if step else sc.line} — «{sc.name}»",
            f"шаг: [{who}] {step.source if step else ''}",
            f"ошибка: {e}",
            "",
            f"экран игрока {who}:",
            indent(describe(chats[who], with_field=True)),
            "",
            "переписка до этого (последние шаги):",
            *log[-8:],
        ])) from None
    finally:
        await world.close()


def main(argv: List[str]) -> int:
    paths = argv or sorted(SCENARIOS_DIR.glob("*.scenario"))
    failed = 0
    for sc in load(paths):
        transcript: List[str] = []
        print(f"\n=== {sc.id}{' (черновик)' if sc.draft else ''}")
        try:
            asyncio.run(run(sc, transcript, verbose=True))
            print("\n".join(transcript))
            print("--- ок")
        except ScenarioFailed as e:
            failed += 1
            print(f"--- НЕ ПРОШЁЛ\n{e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
