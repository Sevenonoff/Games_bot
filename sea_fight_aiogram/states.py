from aiogram.fsm.state import State, StatesGroup


class MultiplayerStates(StatesGroup):
    """Состояния FSM для мультиплеера"""

    # Главное меню мультиплеера
    main_menu = State()

    # Выбор времени на ход
    choosing_time_limit = State()

    # Выбор набора кораблей
    choosing_ship_set = State()

    # Расстановка кораблей (ручная)
    placing_ships_manual = State()

    # Выбор режима расстановки
    choosing_placement_mode = State()

    # Ожидание второго игрока
    waiting_for_opponent = State()

    # Ожидание "Готов играть"
    waiting_ready = State()

    # Игра в процессе
    playing = State()

    # Конец игры
    game_over = State()


class SinglePlayerStates(StatesGroup):
    """Состояния FSM для одиночной игры"""
    choosing_ship_set = State()
