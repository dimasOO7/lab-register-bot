from contextlib import asynccontextmanager
from datetime import date
from typing import List, Optional, Tuple
import aiosqlite

from src.database.models import User, Lesson, QueueEntry


class Repository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @asynccontextmanager
    async def _get_conn(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON;")
            yield db

    # ================= USER OPERATIONS =================

    async def upsert_user(self, user_id: int, username: Optional[str], full_name: str) -> User:
        query = """
        INSERT INTO users (user_id, username, full_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            full_name = excluded.full_name
        RETURNING user_id, username, full_name, created_at;
        """
        async with self._get_conn() as conn:
            cursor = await conn.execute(query, (user_id, username, full_name.strip()))
            row = await cursor.fetchone()
            await conn.commit()
            return User(
                user_id=row["user_id"],
                username=row["username"],
                full_name=row["full_name"],
                created_at=row["created_at"],
            )

    async def get_user(self, user_id: int) -> Optional[User]:
        query = "SELECT user_id, username, full_name, created_at FROM users WHERE user_id = ?;"
        async with self._get_conn() as conn:
            cursor = await conn.execute(query, (user_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            return User(
                user_id=row["user_id"],
                username=row["username"],
                full_name=row["full_name"],
                created_at=row["created_at"],
            )

    async def update_user_name(self, user_id: int, full_name: str) -> bool:
        query = "UPDATE users SET full_name = ? WHERE user_id = ?;"
        async with self._get_conn() as conn:
            cursor = await conn.execute(query, (full_name.strip(), user_id))
            await conn.commit()
            return cursor.rowcount > 0

    # ================= LESSON OPERATIONS =================

    async def create_lesson(
        self,
        subject: str,
        datetime_str: str,
        lesson_date: str,
        description: Optional[str],
        max_slots: int,
        created_by: int,
        external_id: Optional[str] = None,
    ) -> Lesson:
        query = """
        INSERT INTO lessons (subject, datetime_str, lesson_date, description, max_slots, created_by, external_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id, subject, datetime_str, lesson_date, description, max_slots, is_active, created_by, created_at, external_id;
        """
        async with self._get_conn() as conn:
            cursor = await conn.execute(
                query,
                (subject.strip(), datetime_str.strip(), lesson_date.strip(), description, max_slots, created_by, external_id),
            )
            row = await cursor.fetchone()
            await conn.commit()
            return Lesson(
                id=row["id"],
                subject=row["subject"],
                datetime_str=row["datetime_str"],
                lesson_date=row["lesson_date"],
                description=row["description"],
                max_slots=row["max_slots"],
                is_active=bool(row["is_active"]),
                created_by=row["created_by"],
                created_at=row["created_at"],
                external_id=row["external_id"],
            )

    async def get_lesson_by_id(self, lesson_id: int) -> Optional[Lesson]:
        query = """
        SELECT id, subject, datetime_str, lesson_date, description, max_slots, is_active, created_by, created_at, external_id
        FROM lessons
        WHERE id = ?;
        """
        async with self._get_conn() as conn:
            cursor = await conn.execute(query, (lesson_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            return Lesson(
                id=row["id"],
                subject=row["subject"],
                datetime_str=row["datetime_str"],
                lesson_date=row["lesson_date"],
                description=row["description"],
                max_slots=row["max_slots"],
                is_active=bool(row["is_active"]),
                created_by=row["created_by"],
                created_at=row["created_at"],
                external_id=row["external_id"],
            )

    async def get_active_lessons(self, auto_cleanup: bool = True) -> List[Lesson]:
        if auto_cleanup:
            await self.cleanup_expired_lessons()

        query = """
        SELECT id, subject, datetime_str, lesson_date, description, max_slots, is_active, created_by, created_at, external_id
        FROM lessons
        WHERE is_active = 1
        ORDER BY lesson_date ASC, id ASC;
        """
        async with self._get_conn() as conn:
            cursor = await conn.execute(query)
            rows = await cursor.fetchall()
            return [
                Lesson(
                    id=row["id"],
                    subject=row["subject"],
                    datetime_str=row["datetime_str"],
                    lesson_date=row["lesson_date"],
                    description=row["description"],
                    max_slots=row["max_slots"],
                    is_active=bool(row["is_active"]),
                    created_by=row["created_by"],
                    created_at=row["created_at"],
                    external_id=row["external_id"],
                )
                for row in rows
            ]

    async def delete_lesson(self, lesson_id: int) -> bool:
        async with self._get_conn() as conn:
            cursor = await conn.execute("SELECT external_id FROM lessons WHERE id = ?;", (lesson_id,))
            row = await cursor.fetchone()
            if row and row["external_id"]:
                await conn.execute(
                    "INSERT OR IGNORE INTO deleted_external_events (external_id) VALUES (?);",
                    (row["external_id"],),
                )
            del_cursor = await conn.execute("DELETE FROM lessons WHERE id = ?;", (lesson_id,))
            await conn.commit()
            return del_cursor.rowcount > 0

    async def sync_external_lesson(
        self,
        subject: str,
        datetime_str: str,
        lesson_date: str,
        description: Optional[str],
        max_slots: int,
        created_by: int,
        external_id: str,
    ) -> Tuple[bool, Optional[Lesson]]:
        async with self._get_conn() as conn:
            # If previously deleted by admin, do not recreate
            c_del = await conn.execute(
                "SELECT external_id FROM deleted_external_events WHERE external_id = ?;",
                (external_id,),
            )
            if await c_del.fetchone():
                return False, None

            # If already exists, return existing
            c_exist = await conn.execute(
                """
                SELECT id, subject, datetime_str, lesson_date, description, max_slots, is_active, created_by, created_at, external_id
                FROM lessons WHERE external_id = ?;
                """,
                (external_id,),
            )
            row = await c_exist.fetchone()
            if row:
                return False, Lesson(
                    id=row["id"],
                    subject=row["subject"],
                    datetime_str=row["datetime_str"],
                    lesson_date=row["lesson_date"],
                    description=row["description"],
                    max_slots=row["max_slots"],
                    is_active=bool(row["is_active"]),
                    created_by=row["created_by"],
                    created_at=row["created_at"],
                    external_id=row["external_id"],
                )

            # Insert newly discovered lesson
            query = """
            INSERT INTO lessons (subject, datetime_str, lesson_date, description, max_slots, created_by, external_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id, subject, datetime_str, lesson_date, description, max_slots, is_active, created_by, created_at, external_id;
            """
            cursor = await conn.execute(
                query,
                (subject.strip(), datetime_str.strip(), lesson_date.strip(), description, max_slots, created_by, external_id),
            )
            row_ins = await cursor.fetchone()
            await conn.commit()
            return True, Lesson(
                id=row_ins["id"],
                subject=row_ins["subject"],
                datetime_str=row_ins["datetime_str"],
                lesson_date=row_ins["lesson_date"],
                description=row_ins["description"],
                max_slots=row_ins["max_slots"],
                is_active=bool(row_ins["is_active"]),
                created_by=row_ins["created_by"],
                created_at=row_ins["created_at"],
                external_id=row_ins["external_id"],
            )

    async def cleanup_expired_lessons(self) -> int:
        """
        Deletes lessons whose date is strictly before today (i.e. day has passed).
        Associated queue entries are automatically deleted via ON DELETE CASCADE.
        """
        today_iso = date.today().isoformat()
        query = "DELETE FROM lessons WHERE lesson_date < ?;"
        async with self._get_conn() as conn:
            cursor = await conn.execute(query, (today_iso,))
            deleted = cursor.rowcount
            await conn.commit()
            return deleted

    # ================= QUEUE OPERATIONS =================

    async def get_queue_for_lesson(self, lesson_id: int) -> List[QueueEntry]:
        query = """
        SELECT q.id, q.lesson_id, q.user_id, q.position, q.created_at,
               u.full_name as user_full_name, u.username as user_username
        FROM queue_entries q
        LEFT JOIN users u ON q.user_id = u.user_id
        WHERE q.lesson_id = ?
        ORDER BY q.position ASC;
        """
        async with self._get_conn() as conn:
            cursor = await conn.execute(query, (lesson_id,))
            rows = await cursor.fetchall()
            return [
                QueueEntry(
                    id=row["id"],
                    lesson_id=row["lesson_id"],
                    user_id=row["user_id"],
                    position=row["position"],
                    created_at=row["created_at"],
                    user_full_name=row["user_full_name"] or "Неизвестный",
                    user_username=row["user_username"],
                )
                for row in rows
            ]

    async def get_user_entry(self, lesson_id: int, user_id: int) -> Optional[QueueEntry]:
        query = """
        SELECT q.id, q.lesson_id, q.user_id, q.position, q.created_at,
               u.full_name as user_full_name, u.username as user_username
        FROM queue_entries q
        LEFT JOIN users u ON q.user_id = u.user_id
        WHERE q.lesson_id = ? AND q.user_id = ?;
        """
        async with self._get_conn() as conn:
            cursor = await conn.execute(query, (lesson_id, user_id))
            row = await cursor.fetchone()
            if not row:
                return None
            return QueueEntry(
                id=row["id"],
                lesson_id=row["lesson_id"],
                user_id=row["user_id"],
                position=row["position"],
                created_at=row["created_at"],
                user_full_name=row["user_full_name"],
                user_username=row["user_username"],
            )

    async def join_queue_at_position(self, lesson_id: int, user_id: int, position: int) -> Tuple[bool, str]:
        """
        Assigns user to a specific slot number `position`.
        Users can choose any positive slot number (including beyond last_occupied + 1).
        If position is occupied by another student -> (False, "Место уже занято...")
        If user is already on this position -> (True, "Вы уже записаны на это место")
        If user is on another position -> moves user to this position.
        If user is not in queue -> assigns user to this position.
        """
        if position < 1 or position > 200:
            return False, "Номер места должен быть числом от 1 до 200."

        async with self._get_conn() as conn:
            # Check who occupies this position
            cursor_occupied = await conn.execute(
                "SELECT position, user_id FROM queue_entries WHERE lesson_id = ? AND position = ?;",
                (lesson_id, position),
            )
            row = await cursor_occupied.fetchone()
            if row:
                if row["user_id"] == user_id:
                    return True, f"Вы уже находитесь на месте #{position}"
                else:
                    return False, f"Место #{position} уже занято другим студентом!"

            # Check if user is already in queue on another position
            cursor_user = await conn.execute(
                "SELECT position FROM queue_entries WHERE lesson_id = ? AND user_id = ?;",
                (lesson_id, user_id),
            )
            user_row = await cursor_user.fetchone()
            if user_row:
                old_pos = user_row["position"]
                # Update position
                await conn.execute(
                    "UPDATE queue_entries SET position = ? WHERE lesson_id = ? AND user_id = ?;",
                    (position, lesson_id, user_id),
                )
                await conn.commit()
                return True, f"Вы успешно переместились с места #{old_pos} на место #{position}!"
            else:
                # Insert new entry
                await conn.execute(
                    "INSERT INTO queue_entries (lesson_id, user_id, position) VALUES (?, ?, ?);",
                    (lesson_id, user_id, position),
                )
                await conn.commit()
                return True, f"Вы успешно записались на место #{position}!"

    async def join_queue_at_first_free(self, lesson_id: int, user_id: int) -> Tuple[bool, str, Optional[int]]:
        """
        Fast sign-up: finds the FIRST free slot (smallest unoccupied position >= 1)
        and places the user there.
        """
        async with self._get_conn() as conn:
            # Check if user is already in queue
            cursor_user = await conn.execute(
                "SELECT position FROM queue_entries WHERE lesson_id = ? AND user_id = ?;",
                (lesson_id, user_id),
            )
            user_row = await cursor_user.fetchone()
            if user_row:
                pos = user_row["position"]
                return False, f"Вы уже записаны в эту очередь на место #{pos}!", pos

            # Get all currently occupied positions
            cursor_occupied = await conn.execute(
                "SELECT position FROM queue_entries WHERE lesson_id = ? ORDER BY position ASC;",
                (lesson_id,),
            )
            occupied_rows = await cursor_occupied.fetchall()
            occupied_set = {r["position"] for r in occupied_rows}

            # Find first free slot >= 1
            first_free = 1
            while first_free in occupied_set:
                first_free += 1

            # Insert at first_free (unlimited growth as needed)
            await conn.execute(
                "INSERT INTO queue_entries (lesson_id, user_id, position) VALUES (?, ?, ?);",
                (lesson_id, user_id, first_free),
            )
            await conn.commit()
            return True, f"Вы успешно записаны на первое свободное место #{first_free}!", first_free

    async def leave_queue(self, lesson_id: int, user_id: int) -> bool:
        async with self._get_conn() as conn:
            cursor = await conn.execute(
                "DELETE FROM queue_entries WHERE lesson_id = ? AND user_id = ?;",
                (lesson_id, user_id),
            )
            await conn.commit()
            return cursor.rowcount > 0
