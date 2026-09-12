import asyncio
import os
from typing import Dict
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from states import GameStates
from keyboards import get_main_menu, create_memory_field
from game_logic import MemoryGame

# Загрузка переменных окружения
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не задан BOT_TOKEN в файле .env")

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Словарь для хранения игр пользователей
user_games: Dict[int, MemoryGame] = {}


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.set_state(GameStates.menu)
    await message.answer(
        "🎮 <b>Развивающий бот</b>\n\n"
        "Выберите игру из меню:",
        reply_markup=get_main_menu()
    )


@dp.callback_query(F.data == "menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.set_state(GameStates.menu)
    user_id = callback.from_user.id
    if user_id in user_games:
        del user_games[user_id]

    await callback.message.edit_text(
        "🎮 <b>Развивающий бот</b>\n\n"
        "Выберите игру из меню:",
        reply_markup=get_main_menu()
    )
    await callback.answer()


@dp.callback_query(F.data == "game_memory")
async def start_memory_game(callback: CallbackQuery, state: FSMContext):
    """Начало игры на память"""
    await state.set_state(GameStates.memory_game)
    user_id = callback.from_user.id

    # Создаем новую игру или получаем существующую
    if user_id not in user_games:
        user_games[user_id] = MemoryGame()

    game = user_games[user_id]
    game.generate_blue_positions()

    # Показываем поле с синими клетками
    await callback.message.edit_text(
        f"🎮 <b>Развитие памяти</b>\n"
        f"Уровень: <b>{game.level}</b>\n"
        f"Запомните {len(game.blue_positions)} синих клеток!\n"
        f"Через 2 секунды они скроются...",
        reply_markup=create_memory_field(
            blue_positions=game.blue_positions
        )
    )
    await callback.answer()

    # Ждем 2 секунды и обновляем поле
    await asyncio.sleep(2)

    await callback.message.edit_text(
        f"🎮 <b>Развитие памяти</b>\n"
        f"Уровень: <b>{game.level}</b>\n"
        f"Нажмите на {len(game.blue_positions)} синих клеток!\n"
        f"Ошибок: {game.mistakes}",
        reply_markup=create_memory_field(
            blue_positions=game.blue_positions,
            clicked_positions=game.clicked_positions
        )
    )


@dp.callback_query(F.data.startswith("cell_"))
async def process_cell_click(callback: CallbackQuery, state: FSMContext):
    """Обработка клика по клетке"""
    if await state.get_state() != GameStates.memory_game:
        await callback.answer("Игра не активна!")
        return

    user_id = callback.from_user.id
    if user_id not in user_games:
        await callback.answer("Игра не найдена!")
        return

    game = user_games[user_id]

    # Извлекаем координаты из callback_data
    _, row_str, col_str = callback.data.split("_")
    row, col = int(row_str), int(col_str)

    # Обрабатываем клик
    game.click_cell(row, col)

    # Обновляем поле
    await callback.message.edit_text(
        f"🎮 <b>Развитие памяти</b>\n"
        f"Уровень: <b>{game.level}</b>\n"
        f"Нажмите на {len(game.blue_positions)} синих клеток!\n"
        f"Ошибок: {game.mistakes}",
        reply_markup=create_memory_field(
            blue_positions=game.blue_positions,
            clicked_positions=game.clicked_positions
        )
    )

    # Проверяем окончание игры
    if game.is_game_over():
        stats = game.get_stats()

        # Определяем результат
        if game.mistakes == 0:
            result_text = "🎉 <b>Отлично! Все верно!</b>"
            next_button_text = "➡️ Следующий уровень"
        elif game.mistakes == 1:
            result_text = "👍 <b>Хорошо! Одна ошибка</b>"
            next_button_text = "🔁 Попробовать снова"
        else:
            result_text = "😕 <b>Попробуйте еще раз</b>"
            next_button_text = "🔁 Ещё раз"

        # Показываем результаты
        await callback.message.edit_text(
            f"🎮 <b>Развитие памяти</b>\n"
            f"Уровень: <b>{game.level}</b>\n\n"
            f"{result_text}\n"
            f"✅ Правильно: {stats['correct']}/{stats['total']}\n"
            f"❌ Ошибок: {game.mistakes}",
            reply_markup=create_memory_field(
                blue_positions=game.blue_positions,
                clicked_positions=game.clicked_positions,
                game_over=True
            )
        )

    await callback.answer()


@dp.callback_query(F.data == "retry")
async def retry_game(callback: CallbackQuery, state: FSMContext):
    """Повтор игры"""
    user_id = callback.from_user.id
    if user_id in user_games:
        game = user_games[user_id]

        # Обрабатываем результат предыдущей игры
        if game.mistakes <= 1:
            # Успешно - повышаем или оставляем уровень
            if game.mistakes == 0 and game.level < game.max_level:
                game.level += 1
            # При 1 ошибке уровень не меняется
        else:
            # Больше 1 ошибки - понижаем уровень
            game.level = max(1, game.level - 1)

        # Сбрасываем игру
        game.reset()

    # Запускаем игру заново
    await start_memory_game(callback, state)


@dp.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    """Показ статистики"""
    user_id = callback.from_user.id
    stats_text = "📊 <b>Статистика</b>\n\n"

    if user_id in user_games:
        game = user_games[user_id]
        stats = game.get_stats()
        stats_text += (
            f"Уровень: <b>{stats['level']}</b>\n"
            f"Точность: <b>{stats['accuracy']:.0%}</b>\n"
            f"Время игры: <b>{stats['time_played']} сек</b>\n"
        )
    else:
        stats_text += "У вас еще нет статистики.\nНачните игру!"

    await callback.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏠 В меню", callback_data="menu")
        ]])
    )
    await callback.answer()


async def main():
    """Запуск бота"""
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())