"""Отладочные команды: сразу попасть в нужное состояние, не протыкивая цепочку.

Доступны только user_id из Manager.debug_users; остальным /dbg показывает их id,
чтобы было что вписать в DEBUG_USER_IDS. Партии, начатые отсюда, — настоящие:
выигрыш попадёт в рекорды, стереть свои данные можно через /dbg reset.
"""
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from . import boats, days as calendar, motivation, notify, path
from . import seafight_mp as mp
from . import seafight_solo as sea
from .progression import WINS_TO_LEVEL_UP
from .sessions import INPUT, Player, Session, TimedSession
from .texts import TITLES, t
from .ui import Button, Reply, Screen, data

if TYPE_CHECKING:
    from .manager import Manager

DAY = 24 * 3600
LEVEL_GAMES = ("memo", "matrix", "tower", "path", "boats")   # «Кораблики»: уровень — самый высокий открытый
SEA_SETS = ("full", "reduced")

HELP = """/dbg level &lt;игра&gt; &lt;уровень&gt; [серия] — уровень и серия побед ({games})
/dbg idle &lt;игра&gt; &lt;дней&gt; — будто последняя игра была N дней назад
/dbg round &lt;сек&gt; — длина партии матрицы для вас (0 — как у всех)
/dbg sea_end [full|reduced] — бой с компьютером за выстрел до победы
/dbg memo_end — мемо, осталась одна пара
/dbg days &lt;N&gt; — будто вы играли N дней подряд до сегодня (мемо и поездка в полдень)
/dbg notify — прислать себе уведомление от друзей, напоминание и итоги недели прямо сейчас
/dbg reset — стереть ваши уровни и рекорды"""

Result = Tuple[Reply, Optional[Session]]


def dispatch(mgr: "Manager", player: Player, args: List[str]) -> Result:
    """Текущая партия к этому моменту уже прервана Manager'ом."""
    handler = COMMANDS.get(args[0].lower() if args else "")
    if handler is None:
        return Reply(menu(mgr, player)), None
    try:
        return handler(mgr, player, args[1:])
    except (ValueError, IndexError, KeyError):
        return Reply(menu(mgr, player, f"⚠️ Не понял: /dbg {' '.join(args)}")), None


def menu(mgr: "Manager", player: Player, status: str = "") -> Screen:
    lines = [status, ""] if status else []
    lines.append("🛠 <b>Отладка</b>")
    for game in LEVEL_GAMES:
        p = mgr.storage.load_progress(mgr.platform, player.user_id, game)
        lines.append(f"{TITLES[game]}: ур. {p.level}, серия {p.win_streak}, "
                     f"ошибок {p.fail_count}, рекорд {p.best_score}")
    round_seconds = mgr.round_overrides.get(player.user_id)
    if round_seconds:
        lines.append(f"⏱ Партия матрицы: {round_seconds} с")
    lines += ["", HELP.format(games=", ".join(LEVEL_GAMES))]
    return Screen("\n".join(lines), [
        [Button("⛵ Выстрел до победы", data("dbg", "sea_end", "reduced")),
         Button("🃏 Последняя пара", data("dbg", "memo_end"))],
        [Button("⏱ Партия 5 с", data("dbg", "round", 5)),
         Button("⏱ Партия 60 с", data("dbg", "round", 0))],
        [Button("🗑 Стереть мой прогресс", data("dbg", "reset"))],
        [Button(t("btn_menu"), "menu")],
    ])


def _level_game(name: str) -> str:
    if name not in LEVEL_GAMES:
        raise ValueError(name)
    return name


def _play_screen(game: str, status: str) -> Screen:
    return Screen(status, [
        [Button(t("btn_play"), data("new", game))],
        [Button("🛠 Отладка", "dbg"), Button(t("btn_menu"), "menu")],
    ])


def set_level(mgr: "Manager", player: Player, args: List[str]) -> Result:
    game, level = _level_game(args[0]), int(args[1])
    streak = int(args[2]) if len(args) > 2 else 0
    if level < 1 or not 0 <= streak < WINS_TO_LEVEL_UP or (game == boats.GAME and level > boats.MAX_LEVEL):
        raise ValueError(args)
    p = mgr.storage.load_progress(mgr.platform, player.user_id, game)
    p.level = p.last_success_level = level
    p.win_streak, p.fail_count = streak, 0
    mgr.storage.save_result(mgr.platform, player.user_id, game, p, None, mgr.clock())
    return Reply(_play_screen(game, f"✅ {TITLES[game]}: уровень {level}, серия побед {streak}")), None


def set_idle(mgr: "Manager", player: Player, args: List[str]) -> Result:
    game, days = _level_game(args[0]), float(args[1])
    if days < 0:
        raise ValueError(args)
    p = mgr.storage.load_progress(mgr.platform, player.user_id, game)
    mgr.storage.save_result(mgr.platform, player.user_id, game, p, None, mgr.clock() - days * DAY)
    return Reply(_play_screen(game, f"✅ {TITLES[game]}: последняя игра {days:g} дн. назад")), None


def set_round(mgr: "Manager", player: Player, args: List[str]) -> Result:
    seconds = int(args[0])
    if seconds < 0:
        raise ValueError(args)
    if seconds:
        mgr.round_overrides[player.user_id] = seconds
        status = f"✅ Партия матрицы: {seconds} с"
    else:
        mgr.round_overrides.pop(player.user_id, None)
        status = f"✅ Партия матрицы: {mgr.round_seconds} с, как у всех"
    return Reply(menu(mgr, player, status)), None


def sea_end(mgr: "Manager", player: Player, args: List[str]) -> Result:
    ship_set = args[0] if args else "reduced"
    if ship_set not in SEA_SETS:
        raise ValueError(args)
    return Reply(mgr.mp.debug_ai_game(player, ship_set)), None


def memo_end(mgr: "Manager", player: Player, args: List[str]) -> Result:
    s = mgr.start_session(player, "memo")
    b = s.board
    pairs: Dict[str, List[int]] = {}
    for i, icon in enumerate(b.cards):
        pairs.setdefault(icon, []).append(i)
    for pair in list(pairs.values())[:-1]:
        for i in pair:
            s.tap(i // b.cols, i % b.cols)
    return Reply(s.screen()), s


def played_days(mgr: "Manager", player: Player, args: List[str]) -> Result:
    n = int(args[0])
    if not 1 <= n <= 400:
        raise ValueError(args)
    today = calendar.day_start(mgr.clock())
    for k in range(n, 0, -1):
        noon = calendar.day_start(today - k * DAY + 12 * 3600) + 12 * 3600
        for game in ("memo", "tower"):
            mgr.storage.add_score(mgr.platform, player.user_id, game, 1, 1, noon)
    j = motivation.journey(mgr.storage, mgr.platform, player.user_id)
    zone, step, size = motivation.zone_of(j.steps)
    return Reply(menu(mgr, player, f"✅ {n} дн. подряд до сегодня: {motivation.zone_title(zone)} — "
                                   f"шаг {step} из {size}, серия {j.streak}")), None


def send_notices(mgr: "Manager", player: Player, args: List[str]) -> Result:
    notify.debug_preview(mgr, player)
    return Reply(menu(mgr, player, "✅ Уведомление от друзей, напоминание и итоги недели — в следующих сообщениях")), None


def reset(mgr: "Manager", player: Player, args: List[str]) -> Result:
    mgr.storage.reset_user(mgr.platform, player.user_id)
    mgr.round_overrides.pop(player.user_id, None)
    return Reply(menu(mgr, player, "✅ Уровни и рекорды стёрты")), None


# --- верный ход: тесты и подсказка dev-сервера Mini App ---

Cell = Tuple[int, int]


def path_next(rnd: path.PathRound) -> Optional[Cell]:
    """Проложи дорогу: следующая клетка кратчайшей дороги, которой ещё нет на поле."""
    return next((x for x in rnd.solution if x not in rnd.road), None)


def right_cell(s: Optional[Session]) -> Optional[Cell]:
    """Верное нажатие в текущей партии; None — сейчас нажимать нечего (показ, итог, конец)."""
    if s is None or s.finished or s.over or s.in_done():
        return None
    if isinstance(s, TimedSession):
        if s.phase != INPUT:
            return None
        if s.game == "matrix":
            return min(s.round.targets - s.round.found)
        if s.game == "path":
            return path_next(s.round)
        by_number = {n: cell for cell, n in s.round.cells.items()}
        return by_number[s.round.numbers[s.round.opened]]
    if s.game == "memo":
        b = s.board
        face_up = b.face_up if len(b.face_up) == 1 else []
        if face_up:
            first = face_up[0]
            idx = next(i for i, icon in enumerate(b.cards)
                       if icon == b.cards[first] and i != first)
        else:
            idx = next(i for i in range(len(b.cards)) if i not in b.matched)
        return divmod(idx, b.cols)
    return None


def hint_payload(mgr: "Manager", uid: int) -> Optional[str]:
    """Payload верного хода игрока сейчас: выстрел по кораблю в бою, клетка в партии,
    «дальше» на итоге раунда; None — ходить нечего (чужой ход, показ, нет партии)."""
    game = mgr.mp.open_game(uid)
    if game is not None:
        if game.status != mp.ACTIVE or game.turn != uid:
            return None
        side, enemy = game.side(uid), {cell for ship in game.opponent(uid).ships for cell in ship}
        cell = next(((r, c) for r in range(sea.ROWS) for c in range(sea.COLS)
                     if side.shots[r][c] == sea.UNKNOWN and (r, c) in enemy), None)
        return data("mpf", game.code, *cell) if cell else None
    s = mgr.sessions.get(uid)
    if s is None or s.finished:
        return None
    if s.in_done():
        return data("t", s.sid, 0, 0)
    cell = right_cell(s)
    return data("t", s.sid, *cell) if cell else None


def boats_plan(mgr: "Manager", uid: int) -> Optional[List[List[int]]]:
    """«Кораблики»: план идеального игрока [[t, r, c], …] по времени игры — для e2e через /dev/hint."""
    s = mgr.sessions.get(uid)
    if not isinstance(s, boats.BoatsSession) or s.finished:
        return None
    return [list(x) for x in boats.perfect_toggles(s.field, s.boats, game_ms=s.game_ms)]


COMMANDS: Dict[str, Callable[["Manager", Player, List[str]], Result]] = {
    "level": set_level,
    "idle": set_idle,
    "round": set_round,
    "sea_end": sea_end,
    "memo_end": memo_end,
    "days": played_days,
    "notify": send_notices,
    "reset": reset,
}
