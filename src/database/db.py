import os
from pathlib import Path
import aiosqlite

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    datetime_str TEXT NOT NULL,
    lesson_date TEXT NOT NULL,
    description TEXT,
    max_slots INTEGER NOT NULL DEFAULT 30,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    external_id TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS queue_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (lesson_id, position),
    UNIQUE (lesson_id, user_id)
);

CREATE TABLE IF NOT EXISTS deleted_external_events (
    external_id TEXT PRIMARY KEY,
    deleted_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_queue_lesson ON queue_entries(lesson_id);
CREATE INDEX IF NOT EXISTS idx_lessons_active_date ON lessons(is_active, lesson_date);
CREATE INDEX IF NOT EXISTS idx_lessons_external_id ON lessons(external_id);
"""


async def init_db(db_path: str):
    db_file = Path(db_path)
    if db_file.parent and str(db_file.parent) != ".":
        db_file.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.executescript(SCHEMA)

        # Migration check: add external_id column if table already existed without it
        cursor = await db.execute("PRAGMA table_info(lessons);")
        columns = [row[1] for row in await cursor.fetchall()]
        if "external_id" not in columns:
            await db.execute("ALTER TABLE lessons ADD COLUMN external_id TEXT UNIQUE;")

        await db.commit()
