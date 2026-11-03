"""Отладочные команды: сразу попасть в нужное состояние, не протыкивая цепочку.

Доступны только user_id из Manager.debug_users; остальным /dbg показывает их id,
чтобы было что вписать в DEBUG_USER_IDS. Партии, начатые отсюда, — настоящие:
выигрыш попадёт в рекорды, стереть свои данные можно через /dbg reset.
"""
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from . import days as calendar, motivation, notify
from .progression import WINS_TO_LEVEL_UP
from .sessions import Player, Session
from .texts import TITLES, t
from .ui import Button, Reply, Screen, data

if TYPE_CHECKING:
    from .manager import Manager

DAY = 24 * 3600
LEVEL_GAMES = ("memo", "matrix", "tower", "path")
SEA_SETS = {"full": "sea_full", "reduced": "sea_reduced"}

HELP = """/dbg level &lt;игра&gt; &lt;уровень&gt; [серия] — уровень и серия побед ({games})
/dbg idle &lt;игра&gt; &lt;дней&gt; — будто последняя игра была N дней назад
/dbg round &lt;сек&gt; — длина партии матрицы для вас (0 — как у всех)
/dbg sea_end [full|reduced] — морской бой за выстрел до победы
/dbg memo_end — мемо, осталась одна пара
/dbg days &lt;N&gt; — будто вы играли N дней подряд до сегодня (мемо и поездка в полдень)
/dbg notify — прислать себе уведомление от друзей и напоминание прямо сейчас
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
    for game in LEVEL_GAMES + tuple(SEA_SETS.values()):
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
    if level < 1 or not 0 <= streak < WINS_TO_LEVEL_UP:
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
    s = mgr.start_session(player, SEA_SETS[args[0] if args else "reduced"])
    cells = [cell for ship in s.board.ships for cell in ship]
    for r, c in cells[:-1]:
        s.tap(r, c)
    return Reply(s.screen()), s


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
    j = motivation.replay(mgr.storage.partias(mgr.platform, player.user_id))
    zone, step, size = motivation.zone_of(j.steps)
    return Reply(menu(mgr, player, f"✅ {n} дн. подряд до сегодня: {motivation.zone_title(zone)} — "
                                   f"шаг {step} из {size}, серия {j.streak}")), None


def send_notices(mgr: "Manager", player: Player, args: List[str]) -> Result:
    notify.debug_preview(mgr, player)
    return Reply(menu(mgr, player, "✅ Уведомление от друзей и напоминание — в следующих сообщениях")), None


def reset(mgr: "Manager", player: Player, args: List[str]) -> Result:
    mgr.storage.reset_user(mgr.platform, player.user_id)
    mgr.round_overrides.pop(player.user_id, None)
    return Reply(menu(mgr, player, "✅ Уровни и рекорды стёрты")), None


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
