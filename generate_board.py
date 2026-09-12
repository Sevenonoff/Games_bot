from games_bot_config import DB_CONFIG, API_TOKEN, BOT_SETTINGS
from bot_messages import get_translation, replace_placeholders

from abc import ABC, abstractmethod
from datetime import datetime
import random
import os
import re
import time



ROWS = 8
COLS = 8
DELAY = 0.4
EMPTY = ' 🟦 '
AVALIABLE = ' 🟩 '
SHIP = ' 🔳 '
BUILDING_SHIP = ' 🔲 '
BANG = ' 💥 '
BIGBANG = ' 💢 '
MISS = ' 💠 '
SHIPS = [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Ship:
    def __init__(self, size, symbol):
        self.size = size
        self.symbol = symbol
        self.coordinates = []
        self.empty_zone = []

    def get_coordinates(self):
        return self.coordinates

    def place(self, x, y, direction, board):
        if direction == 'horizontal':
            self.coordinates = [(x, y + i) for i in range(self.size)]
            self.empty_zone = [(x + dx, y + dy) for dx in range(-1, 2) for dy in range(-1, self.size + 1)]

        elif direction == 'vertical':
            self.coordinates = [(x + i, y) for i in range(self.size)]
            self.empty_zone = [(x + dx, y + dy) for dx in range(-1, self.size + 1) for dy in range(-1, 2)]

        # self.empty_zone = [(x if x >= 0 else 0, y if y >= 0 else 0) for x, y in self.empty_zone]
        # self.empty_zone = [(x if x < board.cols else board.cols-1, y if y < board.rows else board.rows-1) for x, y in self.empty_zone]

        if all(0 <= x < board.rows and 0 <= y < board.cols and board.is_cell_empty(x, y) for x, y in self.coordinates):
            if all(board.is_cell_empty(x, y) for x, y in self.empty_zone if 0 <= x < board.rows and 0 <= y < board.cols):
                board.place_ship(self)
                # print(self.coordinates)
                # print(self.empty_zone)
                return True
        return False



class BaseBoard(ABC):
    def __init__(self, rows, cols, empty_symbol, initial_board=None):
        self.rows = rows
        self.cols = cols
        self.empty_symbol = empty_symbol
        if initial_board:
            self.board = initial_board
        else:
            self.board = [[empty_symbol for _ in range(cols)] for _ in range(rows)]

    def display(self):
        for line in self.board:
            print(" ".join(line))

    @abstractmethod
    def update_cell(self, x, y, symbol):
        pass

class Board(BaseBoard):
    def __init__(self, rows, cols, empty_symbol, initial_board=None):
        super().__init__(rows, cols, empty_symbol, initial_board)

    def is_cell_empty(self, x, y):
        return self.board[x][y] == self.empty_symbol

    def place_ship(self, ship):
        for x, y in ship.get_coordinates():
            self.update_cell(x, y, ship.symbol)

    def is_ship_placed(self, x, y):
        return self.board[x][y] == SHIP

    def update_cell(self, x, y, symbol):
        if 0 <= x < self.rows and 0 <= y < self.cols:
            self.board[x][y] = symbol
        else:
            raise ValueError("Координаты выходят за пределы доски")

class PlayerBoard(BaseBoard):
    def __init__(self, rows, cols, empty_symbol, initial_board=None):
        super().__init__(rows, cols, empty_symbol, initial_board)

    def update_cell(self, x, y, symbol):
        if 0 <= x < self.rows and 0 <= y < self.cols:
            self.board[x][y] = symbol
        else:
            raise ValueError("Координаты выходят за пределы доски")

class GameLogic:
    def __init__(self, rows, cols, empty_symbol, ship_symbol, initial_board=None, initial_player_board=None):
        self.rows = rows
        self.cols = cols
        self.empty_symbol = empty_symbol
        self.ship_symbol = ship_symbol
        self.board = Board(rows, cols, empty_symbol, initial_board)
        self.player_board = PlayerBoard(rows, cols, empty_symbol, initial_player_board)
        self.is_board_generated = False  # Флаг, указывающий, было ли поле сгенерировано

    def generate_board(self, ships):
        if self.is_board_generated:
            return True  # Поле уже сгенерировано
        max_attempts = 20  # Максимальное количество попыток размещения кораблей
        placed = False
        for attempt in range(max_attempts):
            success = True
            print("attempt", attempt, ships)
            board = Board(self.rows, self.cols, self.empty_symbol)

            for ship_size in ships:
                ship = Ship(ship_size, self.ship_symbol)
                placed = False
                tries = 100

                while not placed and tries > 0:

                    x = random.randint(0, self.rows - 1)
                    y = random.randint(0, self.cols - 1)
                    direction = random.choice(['horizontal', 'vertical'])
                    # placed = ship.place(x, y, direction, board)
                    placed = False

                    coordinates = []
                    empty_zone = []

                    if direction == 'horizontal':
                        coordinates = [(x, y + i) for i in range(ship_size)]
                        empty_zone = [(x + dx, y + dy) for dx in range(-1, 2) for dy in range(-1, ship_size + 1)]

                    elif direction == 'vertical':
                        coordinates = [(x + i, y) for i in range(ship_size)]
                        empty_zone = [(x + dx, y + dy) for dx in range(-1, ship_size + 1) for dy in range(-1, 2)]

                    # self.empty_zone = [(x if x >= 0 else 0, y if y >= 0 else 0) for x, y in self.empty_zone]
                    # self.empty_zone = [(x if x < board.cols else board.cols-1, y if y < board.rows else board.rows-1) for x, y in self.empty_zone]

                    if all(0 <= x < board.rows and 0 <= y < board.cols and board.is_cell_empty(x, y) for x, y in
                           coordinates):
                        if all(board.is_cell_empty(x, y) for x, y in empty_zone if
                               0 <= x < board.rows and 0 <= y < board.cols):
                            placed = ship.place(x, y, direction, board)
                            board.place_ship(ship)
                            # board.display()
                            # print(coordinates)
                            # print(empty_zone)
                            placed = True


                    tries -= 1
                    # print(x, " ", y, "tries", tries)

                if not placed:
                    success = False
                    break
                else:

                    print(x, " ", y, "attempt", attempt, "tries", tries)
            board.display()

            if success:
                # Если все корабли успешно размещены, сохраняем поле и возвращаем True
                # board.display()
                return True

        self.is_board_generated = True
        self.board = board
        return True

    def generate_board_long(self, ships):
        if self.is_board_generated:
            return True  # Поле уже сгенерировано
        max_attempts = 10  # Максимальное количество попыток размещения кораблей
        placed = False
        for attempt in range(max_attempts):
            print("attempt", attempt)
            board = Board(self.rows, self.cols, self.empty_symbol)

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
                    break
                else:
                    print(x, " ", y, "attempt", attempt, "tries", tries)

            if placed:
                board.display()
                break

        if not placed:
            return False


        self.is_board_generated = True
        self.board = board
        return True

    def check_if_killed(self, x, y):
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            for i in range(self.rows):
                nx, ny = x + dx * i, y + dy * i
                if 0 <= nx < self.rows and 0 <= ny < self.cols and self.board.is_ship_placed(nx, ny):
                    return False
                elif 0 <= nx < self.rows and 0 <= ny < self.cols and self.board.is_cell_empty(nx, ny):
                    break
        return True


    def check_if_won(self):
        return all(self.board.is_cell_empty(x, y) for x in range(self.rows) for y in range(self.cols))


if __name__ == '__main__':
    game_manager = GameLogic(ROWS, COLS, EMPTY, SHIP)
    game_manager.generate_board(SHIPS)
    print("==============================================")
    print("==============================================")
    print("==============================================")
    game_manager.generate_board_long(SHIPS)