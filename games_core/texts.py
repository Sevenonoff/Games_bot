"""Тексты интерфейса. Пока только русский; ключи общие для будущих языков."""

TITLES = {
    "memo": "🃏 Мемо",
    "matrix": "🟦 Матрица памяти",
    "tower": "🔢 Башня чисел",
    "sea_full": "🚢 Морской бой",
    "sea_reduced": "⛵ Морской бой (малый)",
}

RU = {
    "menu": "🎮 <b>Игры</b>\n\nВыберите игру:",
    "btn_sea": "🚢 Морской бой",
    "btn_records": "🏆 Рекорды",
    "btn_menu": "🏠 Меню",
    "btn_again": "🔁 Ещё раз",
    "btn_play": "▶️ Играть",
    "btn_quit": "🏁 Закончить",
    "sea_choose": "🚢 <b>Морской бой</b>\n\nПоле 8×8. Выберите набор кораблей:",
    "btn_sea_full": "Полный: 4, 3×2, 2×3, 1×4",
    "btn_sea_reduced": "Малый: 3, 2×2, 1×3",
    "records_choose": "🏆 <b>Рекорды</b>\n\nВыберите игру:",
    "records_empty": "Пока никто не играл.",
    "records_mine": "Ваш рекорд: <b>{score}</b>",
    "level": "уровень {level}",
    "timed_status": "Очки: <b>{score}</b> · серия {mult} · ⏱ {left} с",
    "phase_preview": "👀 Запоминайте!",
    "phase_matrix": "👆 Нажмите клетки, которые были синими",
    "phase_tower": "👆 Нажимайте числа по возрастанию",
    "memo_status": "Пары: {found}/{pairs} · Очки: <b>{score}</b> · серия {mult}",
    "memo_hint": "Откройте две карты. Совпали — пара ваша.",
    "sea_status": "Очки: <b>{score}</b> · кораблей осталось: {ships}",
    "sea_hint": "Стреляйте по клеткам: 💥 попадание, 💢 потоплен, 💠 мимо.",
    "note_preview": "Запоминайте…",
    "note_round_ok": "✅ Раунд пройден",
    "note_round_fail": "❌ Ошибка — следующий раунд",
    "note_level_up": "⬆️ Уровень {level}!",
    "note_level_down": "⬇️ Уровень {level}",
    "note_penalty": "−{points}: эту карту вы уже видели",
    "note_hit": "💥 Попадание",
    "note_sunk": "💢 Корабль потоплен!",
    "note_miss": "💠 Мимо",
    "note_stale": "Эта партия уже завершена",
    "result_title": "🏁 <b>Партия окончена</b> · {title}",
    "result_score": "Очки: <b>{score}</b>",
    "result_record_new": "🏆 Новый рекорд!",
    "result_record": "Рекорд: {best}",
    "result_level": "Уровень: {level}",
    "result_rounds": "Раундов пройдено: {won} из {total}",
    "result_memo_done": "Поле собрано за {moves} ходов!",
    "result_memo_quit": "Найдено пар: {found} из {pairs}",
    "result_sea_won": "🎉 Все корабли потоплены!",
    "result_sea_quit": "Бой прерван, результат не записан.",
    "dbg_off": "Отладочные команды недоступны.\nВаш id: <code>{user_id}</code>",
}


def t(key: str, **kwargs) -> str:
    text = RU[key]
    return text.format(**kwargs) if kwargs else text
