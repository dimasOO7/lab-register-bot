import pytest
from datetime import date, timedelta
from src.database.db import init_db
from src.database.repository import Repository


@pytest.fixture
async def repo(tmp_path):
    db_file = tmp_path / "test_text_input.db"
    await init_db(str(db_file))
    return Repository(str(db_file))


@pytest.mark.asyncio
async def test_manual_slot_input_beyond_last_occupied(repo: Repository):
    """
    Verifies that a user can directly occupy any free positive position,
    such as position 10 in an empty queue.
    """
    await repo.upsert_user(1, "user1", "Студент 1")
    await repo.upsert_user(2, "user2", "Студент 2")
    await repo.upsert_user(3, "user3", "Студент 3")

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    lesson = await repo.create_lesson("Алгоритмы", "Завтра", tomorrow, None, 10, 1)

    # 1. In empty queue, user 1 directly occupies slot #10
    ok_10, msg_10 = await repo.join_queue_at_position(lesson.id, user_id=1, position=10)
    assert ok_10 is True
    assert "успешно записались на место #10" in msg_10

    # 2. User 2 tries to take occupied slot #10 -> rejected
    ok_occ, msg_occ = await repo.join_queue_at_position(lesson.id, user_id=2, position=10)
    assert ok_occ is False
    assert "уже занято" in msg_occ

    # 3. User 2 can occupy slot #1 or slot #25
    ok_1, msg_1 = await repo.join_queue_at_position(lesson.id, user_id=2, position=1)
    assert ok_1 is True

    ok_25, msg_25 = await repo.join_queue_at_position(lesson.id, user_id=3, position=25)
    assert ok_25 is True

    # Check queue ordering
    queue = await repo.get_queue_for_lesson(lesson.id)
    positions = [q.position for q in queue]
    assert positions == [1, 10, 25]

    # Invalid positions (<= 0 or > 200)
    ok_zero, _ = await repo.join_queue_at_position(lesson.id, user_id=1, position=0)
    assert ok_zero is False

    ok_neg, _ = await repo.join_queue_at_position(lesson.id, user_id=1, position=-5)
    assert ok_neg is False

    ok_huge, _ = await repo.join_queue_at_position(lesson.id, user_id=1, position=999)
    assert ok_huge is False
