from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class MultiplayerGame:
    game_id: int
    player1_id: int
    player2_id: Optional[int]
    status: str  # waiting, placing, active, finished, abandoned
    join_code: str = ''
    placement_complete1: bool = False
    placement_complete2: bool = False
    placement_mode: str = 'auto'  # auto, manual
    ship_set: str = 'full'  # full, reduced
    current_turn: int = 0
    turn_start_time: Optional[datetime] = None
    time_limit_seconds: Optional[int] = None
    board1: str = ''
    board2: str = ''
    attacks1: str = ''
    attacks2: str = ''
    score1: int = 0
    score2: int = 0
    winner_id: Optional[int] = None
    created_at: datetime = None
    finished_at: Optional[datetime] = None
    last_move_time: Optional[datetime] = None
    timeouts_count1: int = 0
    timeouts_count2: int = 0

    def get_player_number(self, user_id: int) -> int:
        """Вернуть номер игрока (1 или 2)"""
        if user_id == self.player1_id:
            return 1
        elif user_id == self.player2_id:
            return 2
        return 0

    def get_opponent_id(self, user_id: int) -> Optional[int]:
        """Вернуть ID оппонента"""
        if user_id == self.player1_id:
            return self.player2_id
        elif user_id == self.player2_id:
            return self.player1_id
        return None

    def get_board(self, player_num: int) -> str:
        """Получить доску игрока"""
        if player_num == 1:
            return self.board1
        elif player_num == 2:
            return self.board2
        return ''

    def get_attacks(self, player_num: int) -> str:
        """Получить атаки игрока"""
        if player_num == 1:
            return self.attacks1
        elif player_num == 2:
            return self.attacks2
        return ''

    def get_score(self, player_num: int) -> int:
        """Получить счёт игрока"""
        if player_num == 1:
            return self.score1
        elif player_num == 2:
            return self.score2
        return 0

    def update_score(self, player_num: int, delta: int):
        """Обновить счёт игрока"""
        if player_num == 1:
            self.score1 += delta
        elif player_num == 2:
            self.score2 += delta


@dataclass
class MultiplayerStats:
    id: int
    user_id: int
    opponent_id: int
    games_played: int = 0
    games_won: int = 0
    games_lost: int = 0
    last_played_at: datetime = None

    @property
    def win_rate(self) -> float:
        """Процент побед"""
        if self.games_played == 0:
            return 0.0
        return (self.games_won / self.games_played) * 100
