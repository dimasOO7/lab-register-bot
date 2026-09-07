import pytest
from datetime import date, timedelta
from src.database.db import init_db
from src.database.repository import Repository


@pytest.fixture
async def repo(tmp_path):
    db_file = tmp_path / "test.db"
    await init_db(str(db_file))
    return Repository(str(db_file))


@pytest.mark.asyncio
async def test_user_upsert_and_update(repo: Repository):
    user = await repo.upsert_user(1001, "ivanov_tg", "Иван Иванов")
    assert user.user_id == 1001
    assert user.full_name == "Иван Иванов"
    assert user.username == "ivanov_tg"

    fetched = await repo.get_user(1001)
    assert fetched is not None
    assert fetched.full_name == "Иван Иванов"

    updated = await repo.update_user_name(1001, "Иван И. Иванов")
    assert updated is True

    fetched_updated = await repo.get_user(1001)
    assert fetched_updated.full_name == "Иван И. Иванов"


@pytest.mark.asyncio
async def test_lesson_creation_and_auto_cleanup(repo: Repository):
    await repo.upsert_user(1, "admin", "Преподаватель")

    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    # Create past lesson
    past_lesson = await repo.create_lesson(
        subject="Вчерашняя пара",
        datetime_str="Вчера 10:00",
        lesson_date=yesterday.isoformat(),
        description="Прошла",
        max_slots=10,
        created_by=1,
    )

    # Create future lesson
    future_lesson = await repo.create_lesson(
        subject="Завтрашняя пара",
        datetime_str="Завтра 14:00",
        lesson_date=tomorrow.isoformat(),
        description="Будет",
        max_slots=10,
        created_by=1,
    )

    # Check active lessons with auto_cleanup
    active = await repo.get_active_lessons(auto_cleanup=True)
    assert len(active) == 1
    assert active[0].id == future_lesson.id
    assert active[0].subject == "Завтрашняя пара"

    # Verify past lesson was removed from DB
    deleted = await repo.get_lesson_by_id(past_lesson.id)
    assert deleted is None


@pytest.mark.asyncio
async def test_queue_slot_take_and_collision(repo: Repository):
    await repo.upsert_user(1, "stud1", "Студент 1")
    await repo.upsert_user(2, "stud2", "Студент 2")

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    lesson = await repo.create_lesson(
        subject="Физика",
        datetime_str="10.09 10:00",
        lesson_date=tomorrow,
        description="Лаб 1",
        max_slots=5,
        created_by=1,
    )

    # Student 1 takes slot 3
    ok, msg = await repo.join_queue_at_position(lesson.id, user_id=1, position=3)
    assert ok is True
    assert "успешно записались" in msg

    # Student 2 tries to take occupied slot 3
    ok2, msg2 = await repo.join_queue_at_position(lesson.id, user_id=2, position=3)
    assert ok2 is False
    assert "уже занято" in msg2

    # Student 2 takes slot 1
    ok3, msg3 = await repo.join_queue_at_position(lesson.id, user_id=2, position=1)
    assert ok3 is True

    # Check queue state
    queue = await repo.get_queue_for_lesson(lesson.id)
    assert len(queue) == 2
    assert queue[0].position == 1
    assert queue[0].user_id == 2
    assert queue[1].position == 3
    assert queue[1].user_id == 1


@pytest.mark.asyncio
async def test_queue_move_slot(repo: Repository):
    await repo.upsert_user(1, "stud1", "Студент 1")

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    lesson = await repo.create_lesson(
        subject="Математика",
        datetime_str="11.09 12:00",
        lesson_date=tomorrow,
        description=None,
        max_slots=10,
        created_by=1,
    )

    # Takes slot 2
    await repo.join_queue_at_position(lesson.id, user_id=1, position=2)
    entry = await repo.get_user_entry(lesson.id, user_id=1)
    assert entry.position == 2

    # Moves to slot 4
    ok, msg = await repo.join_queue_at_position(lesson.id, user_id=1, position=4)
    assert ok is True
    assert "переместились" in msg

    entry = await repo.get_user_entry(lesson.id, user_id=1)
    assert entry.position == 4

    # Slot 2 is now free
    queue = await repo.get_queue_for_lesson(lesson.id)
    positions = [q.position for q in queue]
    assert 2 not in positions
    assert 4 in positions


@pytest.mark.asyncio
async def test_queue_first_free_slot(repo: Repository):
    """
    Tests fast sign-up: finds the FIRST free slot (lowest unoccupied position >= 1).
    """
    await repo.upsert_user(1, "stud1", "Студент 1")
    await repo.upsert_user(2, "stud2", "Студент 2")
    await repo.upsert_user(3, "stud3", "Студент 3")

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    lesson = await repo.create_lesson(
        subject="Информатика",
        datetime_str="12.09 14:00",
        lesson_date=tomorrow,
        description=None,
        max_slots=3,
        created_by=1,
    )

    # Empty queue -> fast sign up gets slot 1
    ok, msg, pos = await repo.join_queue_at_first_free(lesson.id, user_id=1)
    assert ok is True
    assert pos == 1

    # Student 2 manually takes slot 3 (leaving slot 2 free!)
    await repo.join_queue_at_position(lesson.id, user_id=2, position=3)

    # Student 3 uses fast sign up -> should get slot 2 (first free!)
    ok3, msg3, pos3 = await repo.join_queue_at_first_free(lesson.id, user_id=3)
    assert ok3 is True
    assert pos3 == 2

    # Student 1 tries fast sign up again -> already in queue
    ok_dup, msg_dup, _ = await repo.join_queue_at_first_free(lesson.id, user_id=1)
    assert ok_dup is False
    assert "уже записаны" in msg_dup

    # Now all 3 slots (1, 2, 3) are taken. User 4 attempts fast sign up
    await repo.upsert_user(4, "stud4", "Студент 4")
    ok_full, msg_full, _ = await repo.join_queue_at_first_free(lesson.id, user_id=4)
    assert ok_full is False
    assert "все 3 мест заняты" in msg_full


@pytest.mark.asyncio
async def test_leave_queue(repo: Repository):
    await repo.upsert_user(1, "stud1", "Студент 1")

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    lesson = await repo.create_lesson(
        subject="БД",
        datetime_str="14.09 10:00",
        lesson_date=tomorrow,
        description=None,
        max_slots=5,
        created_by=1,
    )

    await repo.join_queue_at_first_free(lesson.id, 1)
    assert await repo.get_user_entry(lesson.id, 1) is not None

    left = await repo.leave_queue(lesson.id, 1)
    assert left is True
    assert await repo.get_user_entry(lesson.id, 1) is None
