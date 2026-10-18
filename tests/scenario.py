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

from games_core.manager import text_payload
from games_core.sessions import TimedSession
from tests.harness import Chat, World, check_screen, live, right_move, wait_preview, win_round, wrong_moves

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
    (r"пишу (.+)", "send"),
    (r"жму клетку (\d+)[ ,]+(\d+)", "tap"),
    (r"жму (.+)", "click"),
    (r"хожу верно до (.+)", "right_until"),
    (r"хожу верно(?: (\d+) раза?)?", "right"),
    (r"ошибаюсь", "wrong"),
    (r"выигрываю раунд", "win_round"),
    (r"жду (\d+(?:[.,]\d+)?) ?с(?:ек)?", "wait"),
    (r"не вижу (.+)", "not_see"),
    (r"вижу (.+)", "see"),
    (r"без уведомления", "no_note"),
    (r"уведомление (.+)", "note"),
    (r"нет кнопки (.+)", "no_button"),
    (r"есть кнопка (.+)", "has_button"),
    (r"кнопки: (.+)", "buttons"),
    (r"открыто клеток:? (\d+)", "open_cells"),
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
    return [b.text for b in chat.buttons if not b.data.startswith("t:")]


async def do_send(world: World, chat: Chat, text: str) -> None:
    await chat.send(text_payload(unquote(text)))


async def do_click(world: World, chat: Chat, label: str) -> None:
    await chat.click(unquote(label))


async def do_tap(world: World, chat: Chat, r: str, c: str) -> None:
    await chat.tap(int(r), int(c))


async def right_once(world: World, chat: Chat) -> None:
    await wait_preview(world, chat)
    cell = right_move(live(chat))
    assert cell is not None, "сейчас нет верного хода: партии нет или она окончена"
    await chat.tap(*cell)


async def do_right(world: World, chat: Chat, times: str = "1") -> None:
    for _ in range(int(times)):
        await right_once(world, chat)


async def do_right_until(world: World, chat: Chat, text: str) -> None:
    text = unquote(text)
    for _ in range(MAX_MOVES):
        if text in plain(chat.text):
            return
        await right_once(world, chat)
    raise AssertionError(f"за {MAX_MOVES} верных ходов «{text}» так и не появилось")


async def do_wrong(world: World, chat: Chat) -> None:
    await wait_preview(world, chat)
    s = live(chat)
    assert s is not None, "партии нет — ошибиться негде"
    for cell in wrong_moves(s):
        await chat.tap(*cell)


async def do_win_round(world: World, chat: Chat) -> None:
    assert isinstance(live(chat), TimedSession), "«выигрываю раунд» — только в матрице и башне"
    await win_round(world, chat)


async def do_wait(world: World, chat: Chat, seconds: str) -> None:
    await world.time.advance(float(seconds.replace(",", ".")))


async def do_see(world: World, chat: Chat, text: str) -> None:
    assert unquote(text) in plain(chat.text), f"на экране нет «{unquote(text)}»"


async def do_not_see(world: World, chat: Chat, text: str) -> None:
    assert unquote(text) not in plain(chat.text), f"на экране есть «{unquote(text)}», а не должно быть"


async def do_note(world: World, chat: Chat, text: str) -> None:
    assert chat.note is not None and unquote(text) in chat.note, \
        f"ждали уведомление «{unquote(text)}», было {chat.note!r}"


async def do_no_note(world: World, chat: Chat) -> None:
    assert chat.note is None, f"ждали нажатие без уведомления, было {chat.note!r}"


CLOSED_CELLS = ("⬜", "🟨")   # закрытая карта / клетка без числа


async def do_open_cells(world: World, chat: Chat, count: str) -> None:
    cells = [b.text for b in chat.buttons if b.data.startswith("t:")]
    opened = sum(1 for text in cells if text not in CLOSED_CELLS)
    assert opened == int(count), f"открыто клеток: {opened}, ожидалось {count}; поле {cells}"


async def do_has_button(world: World, chat: Chat, label: str) -> None:
    assert any(unquote(label) in x for x in labels(chat)), f"нет кнопки «{unquote(label)}»"


async def do_no_button(world: World, chat: Chat, label: str) -> None:
    assert not any(unquote(label) in x for x in labels(chat)), f"есть кнопка «{unquote(label)}», а не должно быть"


async def do_buttons(world: World, chat: Chat, spec: str) -> None:
    expected = [unquote(x) for x in spec.split("|")]
    actual = labels(chat)
    ok = len(expected) == len(actual) and all(e in a for e, a in zip(expected, actual))
    assert ok, f"кнопки не те:\n  ждали {expected}\n  на экране {actual}"


ACTIONS: Dict[str, Callable] = {
    "send": do_send, "click": do_click, "tap": do_tap,
    "right": do_right, "right_until": do_right_until, "wrong": do_wrong, "win_round": do_win_round,
    "wait": do_wait, "see": do_see, "not_see": do_not_see, "note": do_note, "no_note": do_no_note,
    "has_button": do_has_button, "no_button": do_no_button, "buttons": do_buttons,
    "open_cells": do_open_cells,
}


# --- прогон ---

def describe(chat: Chat, with_field: bool = False) -> str:
    if chat.ref is None:
        return "(бот ещё ничего не прислал)"
    text = plain(chat.text).strip()
    out = text if text else "(пусто)"
    if with_field:
        for row in chat.screen.rows:
            if all(b.data.startswith("t:") for b in row):
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
    world = World(debug_users={ids[a] for a in sc.admins})
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
            if step.action in ("send", "click", "tap", "right", "right_until", "wrong", "win_round", "wait"):
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
