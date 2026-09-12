from aiogram.fsm.state import State, StatesGroup

class GameStates(StatesGroup):
    menu = State()
    memory_game = State()