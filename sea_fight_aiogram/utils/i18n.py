from typing import Dict


def get_translation(language_code: str, key: str) -> str:
    """Получить перевод по ключу"""
    return translations.get(language_code, translations.get('en', {})).get(key, key)


def replace_placeholders(template: str, *args) -> str:
    """Заменить плейсхолдеры в тексте"""
    for i, value in enumerate(args, start=1):
        placeholder = f"%{i}"
        template = template.replace(placeholder, str(value))
    return template


translations: Dict[str, Dict[str, str]] = {
    'en': {
        'text_start_msg': 'Welcome to Sea Fight!',
        "text_sea_fight": "Fight!",
        "text_score": "Score",
        "text_miss": "💨 Miss!",
        "text_damaged": "💢 Hit!",
        "text_killed": "💥 Sunk!",
        'text_you_won': 'Game over',
        'text_leaderboard': '<b>Leaderboard</b>',
        'text_leaderboard_added': "Hooray, I've added you to the leaderboard! %1 is in %2 place with a score of %3!",
        'text_share_msg': "Share your results with friends 👇",
        'text_share_text': "Check it out, I scored %1 points in <a href='https://t.me/games_telegram_robot?start=share'>Sea Battle</a>! Can you score more? 😉",
        'text_win': "⬛⬛⬛⬛⬛⬛⬛\nYou win!\nYour score: %1\n⬛⬛⬛⬛⬛⬛⬛⬛⬛",
        'text_win1': "🟩🟧🟥🟨🟪🟫⬛\nYou win!\nYour score: %1\n🟩🟧🟥🟨🟪🟫⬛",
        'error_text_cant_generate_board': "Failed to place ships on the board.",
        'error_generic': "Something went wrong. Try again.",
        'error_placement_not_found': "Ship placement not found. Start a new game.",
        'error_no_game': "No active game.",
        'error_game_not_active': "This game is already over.",
        'error_no_active_game': "You have no active game.",

        # Last move of each side, shown above the boards
        "text_your_move": "You: %1",
        "text_opponent_move": "Opponent: %1",
        "move_miss": "💨 missed",
        "move_hit": "💢 hit a ship",
        "move_sunk": "💥 sank a ship",

        # Multiplayer rating
        "rating_type_label": "%1 — <b>Player rating</b>",
        "text_rating_change": "Rating: %1 (%2)",
        "btn_back": "← Back",

        "btn_new_game": "Single Game",
        "btn_single_game": "Single Game",
        "btn_leaderboard": "Leaderboard",
        "btn_multiplayer": "Play with Friend",
        "btn_cancel": "Cancel",
        "btn_ready": "I'm Ready",
        "btn_fix_ship": "Lock ship",
        "btn_next_ship": "Next Ship",
        "btn_rotate": "Rotate",
        "btn_give_up": "Give Up",
        "btn_return_game": "Return to Game",
        "btn_main_menu": "🏠 Main menu",

        # Ship set selection
        "text_choose_ship_set": "🚢 Choose ship set:\n\n⚠️ The field is 8×8 due to Telegram limitations. The full set of ships can be tricky to place manually.",
        "ship_set_full": "🚢 Full set (10 ships)",
        "ship_set_reduced": "🛥️ Reduced set (6 ships)",
        "ship_set_full_desc": "4, 3, 3, 2, 2, 2, 1, 1, 1, 1",
        "ship_set_reduced_desc": "3, 2, 2, 1, 1, 1",

        # Placement errors
        "error_ship_out_of_bounds": "❌ Ship goes out of bounds!",
        "error_ship_overlaps": "❌ Ship overlaps another ship!",
        "error_ship_too_close": "❌ Ship is too close to another ship!",

        # Reset placement
        "btn_reset_placement": "🔄 Start over",

        # Timer
        "text_placement_timer": "⏱ Remaining: %1",

        # Leaderboard types
        "text_choose_leaderboard": "🏆 Choose leaderboard:",
        "leaderboard_solo_full": "🎖️ Solo (full set)",
        "leaderboard_solo_reduced": "🎖️ Solo (reduced set)",
        "leaderboard_mp_full": "⚔️ Multiplayer (full set)",
        "leaderboard_mp_reduced": "⚔️ Multiplayer (reduced set)",
        "leaderboard_type_label": "%1 — <b>Leaderboard</b>",

        # Multiplayer
        "text_choose_time_limit": "⏱ Choose time per turn:",
        "text_choose_placement_mode": "🚢 Choose ship placement:",
        "text_waiting_for_opponent": "⏳ Waiting for opponent...\n\nShare this link with a friend:\n%1\n\nGame ID: %2",
        "text_waiting_ready": "✅ Your ships are placed! Waiting for opponent...",
        "text_manual_placement": "🚢 Place your ships:\n\nTap a cell to place the ship center.\nTap the same cell again to rotate.\nThen press Lock to confirm.\nPlace ships from largest to smallest:",
        "text_cancelled": "❌ Cancelled",
        "text_opponent_joined": "🎮 %1 has joined the game!",
        "text_you_joined": "🎮 You joined %1's game!",
        "text_opponent_joined_placement": "🎮 %1 joined the game! Start placing your ships!",
        "text_you_joined_placement": "🎮 You joined %1's game! Start placing your ships!",
        "text_manual_placement_after_join": "🚢 After opponent joins, you'll start placing ships manually.",
        "text_game_not_found": "❌ Game not found or already started",
        "text_game_full": "❌ This game already has two players",
        "text_own_game": "❌ You can't join your own game",
        "text_own_game_hint": "⚠️ This is your invite link. Forward it to a friend to start the game!",
        "error_active_game": "❌ You already have an active game",
        "error_creating_game": "❌ Error creating game",
        "error_not_your_turn": "❌ Not your turn!",
        "error_invalid_move": "❌ Invalid move",
        "time_unlimited": "∞ Unlimited",
        "time_10s": "10 sec",
        "time_30s": "30 sec",
        "time_1m": "1 min",
        "time_5m": "5 min",
        "time_1h": "1 hour",
        "placement_auto": "🎲 Automatic",
        "placement_manual": "✋ Manual",
        "text_multiplayer_in_development": "🚧 Multiplayer is in development\n\n🎮 Coming soon!\n\n⏳ Stay tuned",

        # Placement timeout
        "text_placement_timeout": "⏱ Time's up! Placement cancelled.",

        # Turn and field labels
        "text_your_turn": "Your turn",
        "text_opponent_turn": "Opponent's turn",
        "text_own_ships_field": "🚢 Your ships",
        "text_attack_field": "🎯 Attack opponent",
        "text_own_field_warning": "⚠️ This is your ships field. Use the attack field below to fire!",

        # Turn timer and opponents line shown above the boards
        "text_turn_timer": "⏱ %1 left",
        "text_versus": "⚔️ %1 vs %2",
        "text_you": "You",

        # Invite and game params
        "text_invite_friend": "📨 Forward the link below to a friend so they can join the game!",
        "text_game_params": "🔗 Link to join:\n%1\n\n📋 Game settings:\n• Placement: %2\n• Time per turn: %3\n• Ship set: %4",

        # Turn timer and game results
        "text_turn_timeout": "⏱ Time for the turn is up! The turn passes to the opponent.",
        "text_timeout_victory": "🏆 Your opponent missed too many turns — you win! Score: %1",
        "text_timeout_defeat": "💀 You missed too many turns — technical defeat. Score: %1",
        "text_mp_victory": "🏆 You won! Score: %1",
        "text_mp_defeat": "💀 You lost... Score: %1",
        "text_game_lost_restart": "❌ Game not found — it may have been lost after a bot restart. Start a new one 👇",
    },
    'ru': {
        'text_start_msg': 'Добро пожаловать в Морской бой!',
        "text_sea_fight": "В бой!",
        "text_score": "Очки",
        "text_miss": "💨 Мимо!",
        "text_damaged": "💢 Попал!",
        "text_killed": "💥 Потопил!",
        'text_you_won': 'Игра окончена',
        'text_leaderboard': '<b>Таблица рекордов</b>',
        'text_leaderboard_added': "Ура, добавил тебя на доску почета! %1 на %2 месте с результатом %3!",
        'text_share_msg': "Поделись своими результатами с друзьями 👇",
        'text_share_text': "Смотри, я набрал %1 очков в <a href='https://t.me/games_telegram_robot?start=share'>Морской бой</a>! Сможешь набрать больше? 😉",
        'text_win': "⬛⬛⬛⬛⬛⬛⬛\nПобеда!\nТвой результат: %1\n⬛⬛⬛⬛⬛⬛⬛⬛⬛",
        'text_win1': "🟩🟧🟥🟨🟪🟫⬛\nПобеда!\nТвой результат: %1\n🟩🟧🟥🟨🟪🟫⬛",
        'error_text_cant_generate_board': "Не удалось разместить корабли на поле.",
        'error_generic': "Что-то пошло не так. Попробуй ещё раз.",
        'error_placement_not_found': "Расстановка не найдена. Начни новую игру.",
        'error_no_game': "Нет активной игры.",
        'error_game_not_active': "Эта игра уже завершена.",
        'error_no_active_game': "У тебя нет активной игры.",

        # Последний ход каждой стороны, показывается над досками
        "text_your_move": "Вы: %1",
        "text_opponent_move": "Противник: %1",
        "move_miss": "💨 мимо",
        "move_hit": "💢 попадание",
        "move_sunk": "💥 корабль потоплен",

        # Рейтинг мультиплеера
        "rating_type_label": "%1 — <b>Рейтинг игроков</b>",
        "text_rating_change": "Рейтинг: %1 (%2)",
        "btn_back": "← Назад",

        "btn_new_game": "Одиночная игра",
        "btn_single_game": "Одиночная игра",
        "btn_leaderboard": "Таблица рекордов",
        "btn_multiplayer": "Играть с другом",
        "btn_cancel": "Отмена",
        "btn_ready": "Я готов",
        "btn_fix_ship": "Зафиксировать корабль",
        "btn_next_ship": "Следующий корабль",
        "btn_rotate": "Повернуть",
        "btn_give_up": "Сдаться",
        "btn_return_game": "Вернуться к игре",
        "btn_main_menu": "🏠 Главное меню",

        # Выбор набора кораблей
        "text_choose_ship_set": "🚢 Выбери набор кораблей:\n\n⚠️ Поле 8×8 из-за ограничений Telegram. Полный набор кораблей может быть проблематично расставить вручную.",
        "ship_set_full": "🚢 Полный набор (10 кораблей)",
        "ship_set_reduced": "🛥️ Сокращённый набор (6 кораблей)",
        "ship_set_full_desc": "4, 3, 3, 2, 2, 2, 1, 1, 1, 1",
        "ship_set_reduced_desc": "3, 2, 2, 1, 1, 1",

        # Ошибки расстановки
        "error_ship_out_of_bounds": "❌ Корабль выходит за границы поля!",
        "error_ship_overlaps": "❌ Корабль пересекается с другим кораблём!",
        "error_ship_too_close": "❌ Корабль слишком близко к другому кораблю!",

        # Сброс расстановки
        "btn_reset_placement": "🔄 Начать расстановку сначала",

        # Таймер
        "text_placement_timer": "⏱ Осталось: %1",

        # Типы лидерборда
        "text_choose_leaderboard": "🏆 Выбери таблицу рекордов:",
        "leaderboard_solo_full": "🎖️ Одиночная (полный набор)",
        "leaderboard_solo_reduced": "🎖️ Одиночная (сокращённый набор)",
        "leaderboard_mp_full": "⚔️ Мультиплеер (полный набор)",
        "leaderboard_mp_reduced": "⚔️ Мультиплеер (сокращённый набор)",
        "leaderboard_type_label": "%1 — <b>Таблица рекордов</b>",

        # Мультиплеер
        "text_choose_time_limit": "⏱ Выбери время на ход:",
        "text_choose_placement_mode": "🚢 Выбери расстановку кораблей:",
        "text_waiting_for_opponent": "⏳ Ждём второго игрока...\n\nОтправь эту ссылку другу:\n%1\n\nID игры: %2",
        "text_waiting_ready": "✅ Корабли расставлены! Ждём противника...",
        "text_manual_placement": "🚢 Расставь корабли:\n\nНажми на клетку чтобы поставить центр корабля.\nНажми ещё раз на ту же клетку — повернуть.\nЗатем нажми «Зафиксировать корабль».\nСтавь от большого к маленькому:",
        "text_cancelled": "❌ Отменено",
        "text_opponent_joined": "🎮 %1 присоединился к игре!",
        "text_you_joined": "🎮 Ты подключился к игре против %1!",
        "text_opponent_joined_placement": "🎮 %1 присоединился к игре! Начинай расстановку кораблей!",
        "text_you_joined_placement": "🎮 Ты подключился к игре против %1! Начинай расстановку кораблей!",
        "text_manual_placement_after_join": "🚢 Когда противник присоединится, начнётся ручная расстановка кораблей.",
        "text_game_not_found": "❌ Игра не найдена или уже началась",
        "text_game_full": "❌ В этой игре уже два игрока",
        "text_own_game": "❌ Нельзя присоединиться к своей же игре",
        "text_own_game_hint": "⚠️ Это твоя ссылка для приглашения друга. Перешли её другу, чтобы начать игру!",
        "error_active_game": "❌ У тебя уже есть активная игра",
        "error_creating_game": "❌ Ошибка создания игры",
        "error_not_your_turn": "❌ Не твой ход!",
        "error_invalid_move": "❌ Неверный ход",
        "time_unlimited": "∞ Без ограничений",
        "time_10s": "10 сек",
        "time_30s": "30 сек",
        "time_1m": "1 мин",
        "time_5m": "5 мин",
        "time_1h": "1 час",
        "placement_auto": "🎲 Автоматическая",
        "placement_manual": "✋ Ручная",
        "text_multiplayer_in_development": "🚧 Мультиплеер в разработке\n\n🎮 Скоро появится!\n\n⏳ Следите за обновлениями",

        # Таймаут расстановки
        "text_placement_timeout": "⏱ Время вышло! Расстановка отменена.",

        # Ход и метки полей
        "text_your_turn": "Ваш ход",
        "text_opponent_turn": "Ход противника",
        "text_own_ships_field": "🚢 Ваши корабли",
        "text_attack_field": "🎯 Поле для атаки",
        "text_own_field_warning": "⚠️ Это поле ваших кораблей. Для атаки используйте поле ниже!",

        # Таймер хода и строка соперников над досками
        "text_turn_timer": "⏱ осталось %1",
        "text_versus": "⚔️ %1 против %2",
        "text_you": "Вы",

        # Приглашение и параметры игры
        "text_invite_friend": "📨 Перешли ссылку ниже второму игроку, чтобы он мог присоединиться!",
        "text_game_params": "🔗 Ссылка для подключения:\n%1\n\n📋 Параметры игры:\n• Расстановка: %2\n• Время на ход: %3\n• Набор кораблей: %4",

        # Таймер хода и результаты игры
        "text_turn_timeout": "⏱ Время на ход вышло! Ход переходит противнику.",
        "text_timeout_victory": "🏆 Противник пропустил слишком много ходов — победа! Очки: %1",
        "text_timeout_defeat": "💀 Ты пропустил слишком много ходов — техническое поражение. Очки: %1",
        "text_mp_victory": "🏆 Победа! Очки: %1",
        "text_mp_defeat": "💀 Поражение... Очки: %1",
        "text_game_lost_restart": "❌ Игра не найдена — возможно, она потерялась после перезапуска бота. Начни новую 👇",
    }
}
