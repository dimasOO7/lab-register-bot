from src.database.models import Lesson, QueueEntry
from src.keyboards.inline import get_slots_keyboard, get_lessons_keyboard


def test_slots_keyboard_labels():
    entries = [
        QueueEntry(id=1, lesson_id=10, user_id=101, position=1, created_at="now", user_full_name="Иван Иванов"),
        QueueEntry(id=2, lesson_id=10, user_id=102, position=3, created_at="now", user_full_name="Петр Петров"),
    ]

    kb = get_slots_keyboard(
        lesson_id=10,
        queue_entries=entries,
        current_user_id=101,
        page=1,
        per_page=10,
    )

    # Flatten buttons to check labels
    button_texts = [b.text for row in kb.inline_keyboard for b in row]

    # Slot 1 is current user (101) -> should have (Вы)
    assert any("✅ #1 (Вы)" in t for t in button_texts)

    # Slot 2 is free -> 🟢 #2 Свободно
    assert any("🟢 #2 Свободно" in t for t in button_texts)

    # Slot 3 is other user (102) -> 🔴 #3 Петр
    assert any("🔴 #3 Петр" in t for t in button_texts)

    # Slot 4 is free -> 🟢 #4 Свободно (the +1 slot after last occupied)
    assert any("🟢 #4 Свободно" in t for t in button_texts)


def test_lessons_keyboard_counts():
    lessons = [
        Lesson(
            id=1,
            subject="Физика",
            datetime_str="15.09 10:00",
            lesson_date="2026-09-15",
            description=None,
            max_slots=20,
            is_active=True,
            created_by=1,
            created_at="now",
        )
    ]
    counts = {1: 5}

    kb = get_lessons_keyboard(lessons, counts)
    button_texts = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Физика" in t and "(5 чел.)" in t for t in button_texts)


def test_format_queue_text_no_empty_slots():
    from src.handlers.queue import format_queue_text

    lesson = Lesson(
        id=1,
        subject="Базы данных",
        datetime_str="15.09.2026 11:30 - 15:05",
        lesson_date="2026-09-15",
        description="ауд. 510",
        max_slots=15,
        is_active=True,
        created_by=1,
        created_at="now",
    )
    entries = [
        QueueEntry(id=1, lesson_id=1, user_id=101, position=1, created_at="now", user_full_name="Иванов Иван", user_username="ivanov"),
        QueueEntry(id=2, lesson_id=1, user_id=102, position=5, created_at="now", user_full_name="Петров Петр", user_username=None),
    ]

    # Render for user 101
    text = format_queue_text(lesson, entries, current_user_id=101, user_entry=entries[0])

    # Should contain 1. and 5.
    assert "<b>1.</b> <b>Иванов Иван</b> (@ivanov) <i>(Вы)</i>" in text
    assert "<b>5.</b> Петров Петр" in text

    # Must NOT contain [Свободно]
    assert "Свободно" not in text
