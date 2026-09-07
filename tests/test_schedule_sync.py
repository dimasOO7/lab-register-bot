import pytest
from datetime import date
from src.database.db import init_db
from src.database.repository import Repository
from src.services.schedule_sync import parse_and_merge_ics_labs


SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//SSAU//Schedule//EN
X-WR-TIMEZONE:Europe/Samara

BEGIN:VEVENT
DTSTART:20260908T073000Z
DTEND:20260908T090500Z
DESCRIPTION:Кудрина Мария Александровна\\nПодгруппа: 1
LOCATION:Лаба / 510 - 14
SUMMARY: 📘 Компьютерная графика (1)
END:VEVENT

BEGIN:VEVENT
DTSTART:20260908T093000Z
DTEND:20260908T110500Z
DESCRIPTION:Кудрина Мария Александровна\\nПодгруппа: 1
LOCATION:Лаба / 510 - 14
SUMMARY: 📘 Компьютерная графика (1)
END:VEVENT

BEGIN:VEVENT
DTSTART:20260908T073000Z
DTEND:20260908T090500Z
DESCRIPTION:Лёзина Ирина Викторовна\\nПодгруппа: 2
LOCATION:Лаба / 423 - 14
SUMMARY: 📘 Объектно-ориентированное программирование (2)
END:VEVENT

BEGIN:VEVENT
DTSTART:20260908T093000Z
DTEND:20260908T110500Z
DESCRIPTION:Лёзина Ирина Викторовна\\nПодгруппа: 2
LOCATION:Лаба / 423 - 14
SUMMARY: 📘 Объектно-ориентированное программирование (2)
END:VEVENT

BEGIN:VEVENT
DTSTART:20260908T111500Z
DTEND:20260908T125000Z
DESCRIPTION:Лектор Иванов И.И.
LOCATION:Лекция / 308 - 3
SUMMARY: 📗 Высшая математика
END:VEVENT

BEGIN:VEVENT
DTSTART:20260908T130000Z
DTEND:20260908T143500Z
DESCRIPTION:Практик Петров П.П.
LOCATION:Практика / Спортзал
SUMMARY: 📕 Физкультура
END:VEVENT

BEGIN:VEVENT
DTSTART:20260910T111500Z
DTEND:20260910T125000Z
DESCRIPTION:Слобожанина Н.А.\\nПодгруппа: 1
LOCATION:Лаба / 241 - 5
SUMMARY: 📘 Иностранный язык (1)
END:VEVENT

BEGIN:VEVENT
DTSTART:20260930T073000Z
DTEND:20260930T090500Z
DESCRIPTION:Кудрина М.А.\\nПодгруппа: 1
LOCATION:Лаба / 510 - 14
SUMMARY: 📘 Компьютерная графика (1)
END:VEVENT

END:VCALENDAR
"""


@pytest.fixture
async def repo(tmp_path):
    db_file = tmp_path / "test_sync.db"
    await init_db(str(db_file))
    return Repository(str(db_file))


def test_parse_and_merge_consecutive_and_subgroups():
    # Reference date: Monday 2026-09-07
    ref_date = date(2026, 9, 7)
    labs = parse_and_merge_ics_labs(SAMPLE_ICS, reference_date=ref_date)

    # 1. Lectures and Practices must be filtered out
    subjects = [l["subject"] for l in labs]
    assert not any("математика" in s.lower() for s in subjects)
    assert not any("физкультура" in s.lower() for s in subjects)

    # 2. Labs far in the future (> next week, 2026-09-30) must be skipped
    dates = [l["lesson_date"] for l in labs]
    assert "2026-09-30" not in dates

    # 3. Two consecutive pairs of Компьютерная графика (1) must be merged into one
    # Start: 07:30 UTC -> 11:30 Samara; End of second: 11:05 UTC -> 15:05 Samara
    kg = next(l for l in labs if "Компьютерная графика" in l["subject"])
    assert "11:30 - 15:05" in kg["datetime_str"]
    assert "п/г 1" in kg["subject"]

    # 4. At the EXACT SAME TIME, OOP (2) is a SEPARATE lab item
    oop = next(l for l in labs if "Объектно-ориентированное программирование" in l["subject"])
    assert "11:30 - 15:05" in oop["datetime_str"]
    assert "п/г 2" in oop["subject"]

    # 5. Single lab pair Иностранный язык (1)
    # Start: 11:15 UTC -> 15:15 Samara; End: 12:50 UTC -> 16:50 Samara
    foreign = next(l for l in labs if "Иностранный язык" in l["subject"])
    assert "15:15 - 16:50" in foreign["datetime_str"]

    # Exactly 3 labs for current + next week
    assert len(labs) == 3


@pytest.mark.asyncio
async def test_database_sync_deduplication_and_deletion(repo: Repository):
    ref_date = date(2026, 9, 7)
    labs = parse_and_merge_ics_labs(SAMPLE_ICS, reference_date=ref_date)

    # Initial sync
    added_count = 0
    for lab in labs:
        created, _ = await repo.sync_external_lesson(
            subject=lab["subject"],
            datetime_str=lab["datetime_str"],
            lesson_date=lab["lesson_date"],
            description=lab["description"],
            max_slots=15,
            created_by=0,
            external_id=lab["external_id"],
        )
        if created:
            added_count += 1

    assert added_count == 3
    active_before = await repo.get_active_lessons()
    assert len(active_before) == 3

    # Re-syncing should not duplicate anything
    added_again = 0
    for lab in labs:
        created, _ = await repo.sync_external_lesson(
            subject=lab["subject"],
            datetime_str=lab["datetime_str"],
            lesson_date=lab["lesson_date"],
            description=lab["description"],
            max_slots=15,
            created_by=0,
            external_id=lab["external_id"],
        )
        if created:
            added_again += 1

    assert added_again == 0
    active_after = await repo.get_active_lessons()
    assert len(active_after) == 3

    # Admin deletes one of the auto-synced labs (e.g. Компьютерная графика)
    kg_lesson = next(l for l in active_after if "Компьютерная графика" in l.subject)
    deleted = await repo.delete_lesson(kg_lesson.id)
    assert deleted is True

    active_deleted = await repo.get_active_lessons()
    assert len(active_deleted) == 2

    # Now re-sync again: deleted lab should NOT be recreated!
    added_third = 0
    for lab in labs:
        created, _ = await repo.sync_external_lesson(
            subject=lab["subject"],
            datetime_str=lab["datetime_str"],
            lesson_date=lab["lesson_date"],
            description=lab["description"],
            max_slots=15,
            created_by=0,
            external_id=lab["external_id"],
        )
        if created:
            added_third += 1

    assert added_third == 0
    active_final = await repo.get_active_lessons()
    assert len(active_final) == 2
    assert not any("Компьютерная графика" in l.subject for l in active_final)


@pytest.mark.asyncio
async def test_manual_lesson_preserved_alongside_synced(repo: Repository):
    # Manually create a pair
    manual = await repo.create_lesson(
        subject="Ручная пара",
        datetime_str="15.09.2026 10:00",
        lesson_date="2026-09-15",
        description="Создана вручную",
        max_slots=20,
        created_by=123,
    )

    # Sync an auto lab
    ref_date = date(2026, 9, 7)
    labs = parse_and_merge_ics_labs(SAMPLE_ICS, reference_date=ref_date)
    lab = labs[0]

    created, synced_lesson = await repo.sync_external_lesson(
        subject=lab["subject"],
        datetime_str=lab["datetime_str"],
        lesson_date=lab["lesson_date"],
        description=lab["description"],
        max_slots=15,
        created_by=0,
        external_id=lab["external_id"],
    )
    assert created is True

    # Both manual and synced lessons exist in database
    active = await repo.get_active_lessons()
    assert len(active) == 2
    subjects = [l.subject for l in active]
    assert "Ручная пара" in subjects
    assert lab["subject"] in subjects
