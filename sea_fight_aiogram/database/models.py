from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    user_id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    phone_number: Optional[str] = None
    is_bot: bool = False
    language_code: str = 'en'
    is_premium: bool = False
    source: Optional[str] = None
    leaderboard_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'username': self.username,
            'phone_number': self.phone_number,
            'is_bot': self.is_bot,
            'language_code': self.language_code,
            'is_premium': self.is_premium,
            'source': self.source,
            'leaderboard_name': self.leaderboard_name,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


@dataclass
class LeaderboardEntry:
    user_id: int
    name: str
    score: int
    date: datetime
