from typing import List, Tuple, Optional
from dataclasses import dataclass

from config import ROWS, COLS, EMPTY, SHIP


@dataclass
class ShipPlacement:
    """Класс для размещения корабля вручную"""
    size: int
    x: int = -1
    y: int = -1
    direction: str = 'horizontal'  # horizontal — вдоль строки (x), vertical — вдоль столбца (y)
    fixed: bool = False
    coordinates: List[Tuple[int, int]] = None
    forbidden_zone: List[Tuple[int, int]] = None

    def __post_init__(self):
        self.coordinates = []
        self.forbidden_zone = []

    def place_center(self, x: int, y: int):
        """Разместить центр корабля в точке (x, y)"""
        self.x = x
        self.y = y
        self._calculate_coordinates()
        self._calculate_forbidden_zone()

    def rotate(self):
        """Повернуть корабль на 90 градусов"""
        if self.fixed:
            return False

        if self.direction == 'horizontal':
            self.direction = 'vertical'
        else:
            self.direction = 'horizontal'

        self._calculate_coordinates()
        self._calculate_forbidden_zone()
        return True

    def fix(self):
        """Зафиксировать положение корабля"""
        if self.x == -1 or self.y == -1:
            return False
        self.fixed = True
        return True

    def _calculate_coordinates(self):
        """Рассчитать координаты корабля — ставим центром в (x,y), 
        для чётных — центр = левая/верхняя клетка (корабль тянется вправо/вниз)"""
        if self.x == -1 or self.y == -1:
            self.coordinates = []
            return

        # Для корабля размера size, центр = size // 2 (0-indexed offset от начала)
        # Чётные: центр = левая/верхняя клетка
        # Нечётные: центр = средняя клетка
        center_offset = (self.size - 1) // 2

        if self.direction == 'horizontal':
            start_y = self.y - center_offset
            coords = []
            for i in range(self.size):
                cy = start_y + i
                if 0 <= self.x < COLS and 0 <= cy < ROWS:
                    coords.append((self.x, cy))
                else:
                    coords = []
                    break
        else:
            start_x = self.x - center_offset
            coords = []
            for i in range(self.size):
                cx = start_x + i
                if 0 <= cx < COLS and 0 <= self.y < ROWS:
                    coords.append((cx, self.y))
                else:
                    coords = []
                    break

        self.coordinates = coords

    def _calculate_forbidden_zone(self):
        """Рассчитать зону вокруг корабля (куда нельзя ставить другие корабли)"""
        self.forbidden_zone = []

        for (cx, cy) in self.coordinates:
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    fx = cx + dx
                    fy = cy + dy
                    if 0 <= fx < COLS and 0 <= fy < ROWS:
                        if (fx, fy) not in self.forbidden_zone:
                            self.forbidden_zone.append((fx, fy))

    def is_valid(self) -> bool:
        """Проверить, можно ли так разместить корабль"""
        return (
            self.x != -1 and self.y != -1 and
            len(self.coordinates) == self.size
        )

    def reset(self):
        """Полный сброс положения корабля"""
        self.x = -1
        self.y = -1
        self.direction = 'horizontal'
        self.fixed = False
        self.coordinates = []
        self.forbidden_zone = []

    def soft_reset(self):
        """Сбросить координаты, но сохранить направление"""
        old_dir = self.direction
        self.x = -1
        self.y = -1
        self.direction = old_dir
        self.fixed = False
        self.coordinates = []
        self.forbidden_zone = []


class ManualPlacementLogic:
    """Логика ручной расстановки кораблей"""

    def __init__(self, rows: int = 8, cols: int = 8, ship_sizes: List[int] = None):
        self.rows = rows
        self.cols = cols
        self.ships: List[ShipPlacement] = []
        self.current_ship_index = 0

        # Инициализация кораблей от большого к маленькому
        if ship_sizes is None:
            ship_sizes = [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]
        for size in ship_sizes:
            self.ships.append(ShipPlacement(size))

    def place_ship_center(self, x: int, y: int) -> Tuple[bool, str]:
        """Разместить текущий корабль центром в клетке (x, y).
        Возвращает (success, error_key) где error_key — ключ перевода ошибки."""
        if self.current_ship_index >= len(self.ships):
            return False, 'error_invalid_move'

        ship = self.ships[self.current_ship_index]

        if ship.fixed:
            return False, 'error_invalid_move'

        # Пробуем поставить
        ship.place_center(x, y)

        # Проверяем валидность (входит ли в границы)
        if not ship.is_valid():
            ship.soft_reset()
            return False, 'error_ship_out_of_bounds'

        # Проверяем пересечение с уже размещёнными кораблями
        for existing_ship in self.ships:
            if existing_ship.fixed:
                for coord in ship.coordinates:
                    if coord in existing_ship.coordinates:
                        ship.soft_reset()
                        return False, 'error_ship_overlaps'

        # Проверяем близость к другим кораблям (запрещённая зона)
        for existing_ship in self.ships:
            if existing_ship.fixed:
                for coord in ship.coordinates:
                    if coord in existing_ship.forbidden_zone:
                        ship.soft_reset()
                        return False, 'error_ship_too_close'

        return True, ''

    def get_error_reason(self, x: int, y: int) -> str:
        """Проверить конкретную причину, почему нельзя поставить корабль в (x, y).
        Возвращает ключ перевода ошибки."""
        if self.current_ship_index >= len(self.ships):
            return 'error_invalid_move'

        ship = self.ships[self.current_ship_index]
        if ship.fixed:
            return 'error_invalid_move'

        # Временно ставим чтобы проверить
        old_x, old_y, old_dir = ship.x, ship.y, ship.direction
        old_coords, old_forbidden = ship.coordinates[:], ship.forbidden_zone[:]

        ship.place_center(x, y)

        if not ship.is_valid():
            ship.x, ship.y, ship.direction = old_x, old_y, old_dir
            ship.coordinates = old_coords
            ship.forbidden_zone = old_forbidden
            return 'error_ship_out_of_bounds'

        # Проверяем пересечение
        for existing_ship in self.ships:
            if existing_ship.fixed:
                for coord in ship.coordinates:
                    if coord in existing_ship.coordinates:
                        ship.x, ship.y, ship.direction = old_x, old_y, old_dir
                        ship.coordinates = old_coords
                        ship.forbidden_zone = old_forbidden
                        return 'error_ship_overlaps'

        # Проверяем запрещённую зону
        for existing_ship in self.ships:
            if existing_ship.fixed:
                for coord in ship.coordinates:
                    if coord in existing_ship.forbidden_zone:
                        ship.x, ship.y, ship.direction = old_x, old_y, old_dir
                        ship.coordinates = old_coords
                        ship.forbidden_zone = old_forbidden
                        return 'error_ship_too_close'

        # Восстанавливаем
        ship.x, ship.y, ship.direction = old_x, old_y, old_dir
        ship.coordinates = old_coords
        ship.forbidden_zone = old_forbidden
        return ''

    def rotate_current_ship(self) -> Tuple[bool, str]:
        """Повернуть текущий корабль. Возвращает (success, error_key)."""
        if self.current_ship_index >= len(self.ships):
            return False, 'error_invalid_move'

        ship = self.ships[self.current_ship_index]

        if ship.fixed:
            return False, 'error_invalid_move'

        if ship.x == -1 or ship.y == -1:
            return False, 'error_invalid_move'

        # Сохраняем текущее состояние
        old_direction = ship.direction
        old_x, old_y = ship.x, ship.y

        # Пробуем повернуть
        ship.rotate()

        if not ship.is_valid():
            ship.direction = old_direction
            ship.x, ship.y = old_x, old_y
            ship._calculate_coordinates()
            ship._calculate_forbidden_zone()
            return False, 'error_ship_out_of_bounds'

        # Проверяем пересечение с кораблями
        for existing_ship in self.ships:
            if existing_ship.fixed:
                for coord in ship.coordinates:
                    if coord in existing_ship.coordinates:
                        ship.direction = old_direction
                        ship.x, ship.y = old_x, old_y
                        ship._calculate_coordinates()
                        ship._calculate_forbidden_zone()
                        return False, 'error_ship_overlaps'

        # Проверяем пересечение с запрещёнными зонами
        for existing_ship in self.ships:
            if existing_ship.fixed:
                for coord in ship.coordinates:
                    if coord in existing_ship.forbidden_zone:
                        # Откатываем
                        ship.direction = old_direction
                        ship.x, ship.y = old_x, old_y
                        ship._calculate_coordinates()
                        ship._calculate_forbidden_zone()
                        return False, 'error_ship_too_close'

        return True, ''

    def fix_current_ship(self) -> bool:
        """Зафиксировать текущий корабль"""
        if self.current_ship_index >= len(self.ships):
            return False

        ship = self.ships[self.current_ship_index]

        if not ship.is_valid():
            return False

        return ship.fix()

    def next_ship(self) -> bool:
        """Перейти к следующему кораблю"""
        if self.current_ship_index >= len(self.ships):
            return False

        if not self.ships[self.current_ship_index].fixed:
            return False

        self.current_ship_index += 1
        return True

    def is_complete(self) -> bool:
        """Проверить, все ли корабли размещены"""
        for ship in self.ships:
            if not ship.fixed:
                return False
        return True

    def get_current_ship(self) -> Optional[ShipPlacement]:
        """Получить текущий корабль"""
        if self.current_ship_index < len(self.ships):
            return self.ships[self.current_ship_index]
        return None

    def get_board(self) -> List[List[str]]:
        """Получить доску с размещёнными кораблями"""
        board = [[EMPTY for _ in range(self.cols)] for _ in range(self.rows)]

        for ship in self.ships:
            if ship.fixed:
                for (x, y) in ship.coordinates:
                    board[y][x] = SHIP

        return board

    def get_forbidden_zone(self) -> List[Tuple[int, int]]:
        """Получить все запрещённые зоны"""
        forbidden = []

        for ship in self.ships:
            if ship.fixed:
                forbidden.extend(ship.forbidden_zone)

        return forbidden

    def get_ships_summary(self) -> str:
        """Получить сводку о кораблях"""
        summary = []
        for i, ship in enumerate(self.ships):
            if ship.fixed:
                status = "✅"
            elif i == self.current_ship_index:
                status = "👉"
            else:
                status = "⬜"
            summary.append(f"{status} {'█' * ship.size} ({ship.size})")
        return "\n".join(summary)

    def reset_all(self):
        """Сбросить всю расстановку и начать сначала"""
        for ship in self.ships:
            ship.reset()
        self.current_ship_index = 0
