from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    user_id: int
    username: Optional[str]
    full_name: str
    created_at: str


@dataclass
class Lesson:
    id: int
    subject: str
    datetime_str: str
    lesson_date: str  # YYYY-MM-DD for expiration check
    description: Optional[str]
    max_slots: int
    is_active: bool
    created_by: int
    created_at: str


@dataclass
class QueueEntry:
    id: int
    lesson_id: int
    user_id: int
    position: int
    created_at: str
    user_full_name: Optional[str] = None
    user_username: Optional[str] = None
