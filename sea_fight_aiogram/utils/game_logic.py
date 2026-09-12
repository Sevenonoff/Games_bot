import random
from abc import ABC, abstractmethod
from typing import List, Tuple
from dataclasses import dataclass

from config import (
    ROWS, COLS, EMPTY, SHIP, SHIPS, BANG
)


@dataclass
class Ship:
    size: int
    symbol: str
    coordinates: List[Tuple[int, int]] = None
    empty_zone: List[Tuple[int, int]] = None

    def __post_init__(self):
        self.coordinates = []
        self.empty_zone = []

    def place(self, x: int, y: int, direction: str, board: 'Board') -> bool:
        """Разместить корабль на доске"""
        if direction == 'horizontal':
            self.coordinates = [(x, y + i) for i in range(self.size)]
            self.empty_zone = [(x + dx, y + dy) for dx in range(-1, 2)
                             for dy in range(-1, self.size + 1)]
        elif direction == 'vertical':
            self.coordinates = [(x + i, y) for i in range(self.size)]
            self.empty_zone = [(x + dx, y + dy) for dx in range(-1, self.size + 1)
                             for dy in range(-1, 2)]

        if all(0 <= x < board.rows and 0 <= y < board.cols
               and board.is_cell_empty(x, y) for x, y in self.coordinates):
            if all(board.is_cell_empty(x, y) for x, y in self.empty_zone
                   if 0 <= x < board.rows and 0 <= y < board.cols):
                board.place_ship(self)
                return True
        return False


def check_ship_sunk_on_board(board: list, x: int, y: int, rows: int, cols: int, ship_symbol: str, bang_symbol: str) -> bool:
    """Проверить, потоплен ли корабль на позиции (x,y) на 2D-доске.
    Возвращает True если весь корабль уничтожен (все клетки = bang_symbol),
    False если корабль ранен но ещё не потоплен."""
    # Ищем все клетки корабля через BFS/DFS
    visited = set()
    ship_cells = []
    stack = [(x, y)]

    while stack:
        cx, cy = stack.pop()
        if (cx, cy) in visited:
            continue
        visited.add((cx, cy))

        cell = board[cy][cx]
        if cell == ship_symbol or cell == bang_symbol:
            ship_cells.append((cx, cy))
            # Ищем соседние клетки корабля
            for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = cx + ddx, cy + ddy
                if 0 <= nx < cols and 0 <= ny < rows and (nx, ny) not in visited:
                    ncell = board[ny][nx]
                    if ncell == ship_symbol or ncell == bang_symbol:
                        stack.append((nx, ny))

    # Если все клетки корабля = bang_symbol → потоплен
    for sx, sy in ship_cells:
        if board[sy][sx] == ship_symbol:
            return False  # ещё есть непоражённые клетки
    return True


def collect_ship_cells(board: list, x: int, y: int, rows: int, cols: int,
                       symbols: tuple) -> set:
    """Собрать все клетки корабля, проходящего через (x, y), поиском по связности.
    symbols — какие символы считать клетками корабля."""
    visited = set()
    cells = set()
    stack = [(x, y)]

    while stack:
        cx, cy = stack.pop()
        if (cx, cy) in visited:
            continue
        visited.add((cx, cy))
        if board[cy][cx] in symbols:
            cells.add((cx, cy))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < cols and 0 <= ny < rows and (nx, ny) not in visited:
                    stack.append((nx, ny))

    return cells


class BaseBoard(ABC):
    def __init__(self, rows: int, cols: int, empty_symbol: str,
                 initial_board: List[List[str]] = None):
        self.rows = rows
        self.cols = cols
        self.empty_symbol = empty_symbol
        if initial_board:
            self.board = initial_board
        else:
            self.board = [[empty_symbol for _ in range(cols)] for _ in range(rows)]

    @abstractmethod
    def update_cell(self, x: int, y: int, symbol: str):
        pass


class Board(BaseBoard):
    def __init__(self, rows: int, cols: int, empty_symbol: str,
                 initial_board: List[List[str]] = None):
        super().__init__(rows, cols, empty_symbol, initial_board)

    def is_cell_empty(self, x: int, y: int) -> bool:
        return self.board[x][y] == self.empty_symbol

    def place_ship(self, ship: Ship):
        for x, y in ship.get_coordinates():
            self.update_cell(x, y, ship.symbol)

    def is_ship_placed(self, x: int, y: int) -> bool:
        return self.board[x][y] == SHIP

    def update_cell(self, x: int, y: int, symbol: str):
        if 0 <= x < self.rows and 0 <= y < self.cols:
            self.board[x][y] = symbol
        else:
            raise ValueError("Координаты выходят за пределы доски")


class PlayerBoard(BaseBoard):
    def __init__(self, rows: int, cols: int, empty_symbol: str,
                 initial_board: List[List[str]] = None):
        super().__init__(rows, cols, empty_symbol, initial_board)

    def update_cell(self, x: int, y: int, symbol: str):
        if 0 <= x < self.rows and 0 <= y < self.cols:
            self.board[x][y] = symbol
        else:
            raise ValueError("Координаты выходят за пределы доски")


class GameLogic:
    def __init__(self, rows: int, cols: int, empty_symbol: str, ship_symbol: str,
                 initial_board: List[List[str]] = None,
                 initial_player_board: List[List[str]] = None):
        self.rows = rows
        self.cols = cols
        self.empty_symbol = empty_symbol
        self.ship_symbol = ship_symbol
        self.board = Board(rows, cols, empty_symbol, initial_board)
        self.player_board = PlayerBoard(rows, cols, empty_symbol, initial_player_board)
        self.is_board_generated = False

    def generate_board(self, ships: List[int]) -> bool:
        """Генерация доски с кораблями"""
        if self.is_board_generated:
            return True

        max_attempts = 20
        placed = False

        for attempt in range(max_attempts):
            board = Board(self.rows, self.cols, self.empty_symbol)
            success = True

            for ship_size in ships:
                ship = Ship(ship_size, self.ship_symbol)
                placed = False
                tries = 100

                while not placed and tries > 0:
                    x = random.randint(0, self.rows - 1)
                    y = random.randint(0, self.cols - 1)
                    direction = random.choice(['horizontal', 'vertical'])
                    placed = ship.place(x, y, direction, board)
                    tries -= 1

                if not placed:
                    success = False
                    break

            if success:
                self.board = board
                self.is_board_generated = True
                return True

        return False

    def check_if_killed(self, x: int, y: int) -> bool:
        """Проверить, уничтожен ли корабль"""
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            for i in range(1, self.rows):
                nx, ny = x + dx * i, y + dy * i
                if not (0 <= nx < self.rows and 0 <= ny < self.cols):
                    break
                cell = self.board.board[nx][ny]
                if cell == self.ship_symbol:
                    return False
                if cell != BANG:
                    # пустая клетка или промах — корабль в эту сторону кончился
                    break
        return True

    def check_if_won(self) -> bool:
        """Проверить, победил ли игрок"""
        return all(not self.board.is_ship_placed(x, y)
                   for x in range(self.rows) for y in range(self.cols))


# Метод для совместимости со старым кодом
Ship.get_coordinates = lambda self: self.coordinates
