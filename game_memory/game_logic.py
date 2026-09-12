import random
from typing import Set, Tuple, Dict
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MemoryGame:
    """Класс для управления игрой на память"""
    level: int = 1
    blue_positions: Set[Tuple[int, int]] = None
    clicked_positions: Dict[Tuple[int, int], bool] = None
    start_time: datetime = None
    mistakes: int = 0
    max_level: int = 10  # Максимум 20 синих клеток (8x8=64 клетки, но можно менять)

    def __post_init__(self):
        if self.blue_positions is None:
            self.blue_positions = set()
        if self.clicked_positions is None:
            self.clicked_positions = {}
        if self.start_time is None:
            self.start_time = datetime.now()

    def generate_blue_positions(self, field_size: int = 8) -> None:
        """Генерация случайных синих позиций"""
        num_blue = min(4 + (self.level - 1), 20)  # Начинаем с 4, макс 20
        self.blue_positions.clear()

        # Генерируем уникальные позиции
        while len(self.blue_positions) < num_blue:
            row = random.randint(0, field_size - 1)
            col = random.randint(0, field_size - 1)
            self.blue_positions.add((row, col))

    def click_cell(self, row: int, col: int) -> bool:
        """Обработка клика по клетке"""
        pos = (row, col)

        # Проверяем, была ли уже нажата эта клетка
        if pos in self.clicked_positions:
            return False

        # Проверяем, правильная ли клетка
        is_correct = pos in self.blue_positions
        self.clicked_positions[pos] = is_correct

        if not is_correct:
            self.mistakes += 1

        return is_correct

    def is_game_over(self) -> bool:
        """Проверка окончания игры"""
        return len(self.clicked_positions) >= min(4 + (self.level - 1), 20)

    def next_level(self) -> bool:
        """Переход на следующий уровень"""
        if self.mistakes == 0:
            self.level += 1
            return True
        elif self.mistakes == 1:
            # Остаемся на том же уровне
            return True
        else:
            # Больше 1 ошибки - опускаемся на уровень ниже
            self.level = max(1, self.level - 1)
            return False

    def get_stats(self) -> dict:
        """Статистика игры"""
        correct = sum(1 for v in self.clicked_positions.values() if v)
        total = len(self.blue_positions)

        return {
            "level": self.level,
            "correct": correct,
            "total": total,
            "accuracy": correct / total if total > 0 else 0,
            "mistakes": self.mistakes,
            "time_played": (datetime.now() - self.start_time).seconds
        }

    def reset(self) -> None:
        """Сброс текущей игры (для повторной попытки)"""
        self.clicked_positions.clear()
        self.mistakes = 0
        self.start_time = datetime.now()