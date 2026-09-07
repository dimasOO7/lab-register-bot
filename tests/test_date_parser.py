from datetime import date, timedelta
from src.utils.date_parser import parse_lesson_datetime


def test_parse_full_date_with_time():
    res = parse_lesson_datetime("15.09.2026 14:00")
    assert res is not None
    display, date_iso = res
    assert display == "15.09.2026 14:00"
    assert date_iso == "2026-09-15"


def test_parse_full_date_without_time():
    res = parse_lesson_datetime("15.09.2026")
    assert res is not None
    display, date_iso = res
    assert display == "15.09.2026"
    assert date_iso == "2026-09-15"


def test_parse_short_date_with_time():
    res = parse_lesson_datetime("20.10 10:30")
    assert res is not None
    display, date_iso = res
    assert "20.10" in display
    assert "10:30" in display
    assert date_iso.endswith("-10-20")


def test_parse_today_and_tomorrow():
    today = date.today()
    tomorrow = today + timedelta(days=1)

    res_today = parse_lesson_datetime("сегодня 12:00")
    assert res_today is not None
    assert res_today[1] == today.isoformat()
    assert "12:00" in res_today[0]

    res_tomorrow = parse_lesson_datetime("завтра 09:30")
    assert res_tomorrow is not None
    assert res_tomorrow[1] == tomorrow.isoformat()
    assert "09:30" in res_tomorrow[0]


def test_invalid_date():
    assert parse_lesson_datetime("invalid_date_string") is None
    assert parse_lesson_datetime("32.13.2026") is None
