import re
from datetime import datetime, date, timedelta
from typing import Optional, Tuple


def parse_lesson_datetime(raw_text: str) -> Optional[Tuple[str, str]]:
    """
    Parses user input into (display_str, date_iso).
    date_iso is in format YYYY-MM-DD for expiration comparison.
    display_str is formatted for nice display (e.g. '15.09.2026 14:00' or '15.09.2026').

    Supported formats:
      - 15.09.2026 14:00
      - 15.09.2026
      - 15.09 14:00 (infers current/next year)
      - 15.09
      - сегодня / сегодня 14:00
      - завтра / завтра 14:00
    """
    text = raw_text.strip().lower()
    now = datetime.now()
    today = now.date()

    # Check words: сегодня / завтра
    time_part = ""
    target_date = None

    if text.startswith("сегодня"):
        target_date = today
        rest = text[len("сегодня"):].strip()
        time_part = rest
    elif text.startswith("завтра"):
        target_date = today + timedelta(days=1)
        rest = text[len("завтра"):].strip()
        time_part = rest

    if target_date is not None:
        # Check if time_part is valid time HH:MM
        time_match = re.search(r"(\d{1,2})[:.-](\d{2})", time_part)
        if time_match:
            hh, mm = int(time_match.group(1)), int(time_match.group(2))
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                display = f"{target_date.strftime('%d.%m.%Y')} {hh:02d}:{mm:02d}"
                return display, target_date.strftime("%Y-%m-%d")
        display = target_date.strftime("%d.%m.%Y")
        return display, target_date.strftime("%Y-%m-%d")

    # Pattern DD.MM.YYYY HH:MM or DD.MM.YYYY
    m_full = re.search(r"^(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})(?:\s+(\d{1,2})[:.-](\d{2}))?$", raw_text.strip())
    if m_full:
        day = int(m_full.group(1))
        month = int(m_full.group(2))
        year = int(m_full.group(3))
        hh = int(m_full.group(4)) if m_full.group(4) is not None else None
        mm = int(m_full.group(5)) if m_full.group(5) is not None else None

        try:
            d = date(year, month, day)
            if hh is not None and mm is not None:
                if 0 <= hh <= 23 and 0 <= mm <= 59:
                    display = f"{day:02d}.{month:02d}.{year} {hh:02d}:{mm:02d}"
                    return display, d.strftime("%Y-%m-%d")
            display = f"{day:02d}.{month:02d}.{year}"
            return display, d.strftime("%Y-%m-%d")
        except ValueError:
            return None

    # Pattern DD.MM HH:MM or DD.MM
    m_short = re.search(r"^(\d{1,2})[./\-](\d{1,2})(?:\s+(\d{1,2})[:.-](\d{2}))?$", raw_text.strip())
    if m_short:
        day = int(m_short.group(1))
        month = int(m_short.group(2))
        year = today.year
        hh = int(m_short.group(3)) if m_short.group(3) is not None else None
        mm = int(m_short.group(4)) if m_short.group(4) is not None else None

        try:
            # If month is earlier in the year, check if it should be next year
            d = date(year, month, day)
            if d < today - timedelta(days=60):
                d = date(year + 1, month, day)
                year = year + 1

            if hh is not None and mm is not None:
                if 0 <= hh <= 23 and 0 <= mm <= 59:
                    display = f"{day:02d}.{month:02d}.{year} {hh:02d}:{mm:02d}"
                    return display, d.strftime("%Y-%m-%d")
            display = f"{day:02d}.{month:02d}.{year}"
            return display, d.strftime("%Y-%m-%d")
        except ValueError:
            return None

    return None
