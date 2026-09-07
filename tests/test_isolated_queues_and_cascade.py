import pytest
from datetime import date, timedelta
from src.database.db import init_db
from src.database.repository import Repository


@pytest.fixture
async def repo(tmp_path):
    db_file = tmp_path / "test_iso.db"
    await init_db(str(db_file))
    return Repository(str(db_file))


@pytest.mark.asyncio
async def test_isolated_queues_for_different_lessons(repo: Repository):
    """
    Verifies that each lesson has its own independent queue and slot assignments.
    """
    await repo.upsert_user(1, "user1", "Алиса")
    await repo.upsert_user(2, "user2", "Боб")

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    lesson_a = await repo.create_lesson("ОС", "15.09 10:00", tomorrow, None, 10, 1)
    lesson_b = await repo.create_lesson("БД", "15.09 14:00", tomorrow, None, 10, 1)

    # In lesson A, Alice takes slot 1, Bob takes slot 2
    await repo.join_queue_at_position(lesson_a.id, user_id=1, position=1)
    await repo.join_queue_at_position(lesson_a.id, user_id=2, position=2)

    # In lesson B, Bob takes slot 1, Alice takes slot 2
    await repo.join_queue_at_position(lesson_b.id, user_id=2, position=1)
    await repo.join_queue_at_position(lesson_b.id, user_id=1, position=2)

    queue_a = await repo.get_queue_for_lesson(lesson_a.id)
    queue_b = await repo.get_queue_for_lesson(lesson_b.id)

    assert len(queue_a) == 2
    assert queue_a[0].user_id == 1 and queue_a[0].position == 1
    assert queue_a[1].user_id == 2 and queue_a[1].position == 2

    assert len(queue_b) == 2
    assert queue_b[0].user_id == 2 and queue_b[0].position == 1
    assert queue_b[1].user_id == 1 and queue_b[1].position == 2


@pytest.mark.asyncio
async def test_cascade_delete_on_expired_lesson(repo: Repository):
    """
    Verifies that when an expired lesson is cleaned up, its queue entries are cascade-deleted.
    """
    await repo.upsert_user(1, "user1", "Алиса")
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    lesson = await repo.create_lesson("Старая пара", "Вчера", yesterday, None, 5, 1)
    await repo.join_queue_at_position(lesson.id, user_id=1, position=1)

    queue_before = await repo.get_queue_for_lesson(lesson.id)
    assert len(queue_before) == 1

    # Cleanup expired
    cleaned = await repo.cleanup_expired_lessons()
    assert cleaned == 1

    queue_after = await repo.get_queue_for_lesson(lesson.id)
    assert len(queue_after) == 0


@pytest.mark.asyncio
async def test_user_name_update_reflected_in_queue(repo: Repository):
    """
    Verifies that when a user updates their name, the queue listing immediately reflects it.
    """
    user = await repo.upsert_user(1, "user1", "Старое Имя")
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    lesson = await repo.create_lesson("Сети", "Завтра", tomorrow, None, 5, 1)

    await repo.join_queue_at_position(lesson.id, user_id=1, position=1)
    queue = await repo.get_queue_for_lesson(lesson.id)
    assert queue[0].user_full_name == "Старое Имя"

    # User changes their name
    await repo.update_user_name(1, "Новое Имя")
    queue_updated = await repo.get_queue_for_lesson(lesson.id)
    assert queue_updated[0].user_full_name == "Новое Имя"
