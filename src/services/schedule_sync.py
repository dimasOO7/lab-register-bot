import re
import logging
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional, Tuple, Dict
import zoneinfo
import aiohttp

from src.database.repository import Repository

logger = logging.getLogger("schedule_sync")
SAMARA_TZ = zoneinfo.ZoneInfo("Europe/Samara")


def normalize_title(raw_title: str) -> str:
    """Collapses spaces, trims, and ensures first letter is capitalized."""
    cleaned = re.sub(r"\s+", " ", raw_title).strip()
    if not cleaned:
        return ""
    return cleaned[:1].upper() + cleaned[1:]


def parse_and_merge_ics_labs(
    ics_content: str,
    reference_date: Optional[date] = None,
) -> List[Dict]:
    """
    Parses ICS calendar, extracts laboratory works,
    filters for current + next week (skipping past days),
    and merges consecutive double pairs for the same discipline & subgroup.
    """
    events_raw = ics_content.split("BEGIN:VEVENT")[1:]
    raw_labs = []

    for ev in events_raw:
        ev_text = ev.split("END:VEVENT")[0]
        loc_m = re.search(r"LOCATION:(.*?)(?:\r?\n|$)", ev_text)
        sum_m = re.search(r"SUMMARY:(.*?)(?:\r?\n|$)", ev_text)
        desc_m = re.search(r"DESCRIPTION:(.*?)(?:\r?\n[A-Z\-]+:|$)", ev_text, re.DOTALL)
        st_m = re.search(r"DTSTART:([0-9TZ]+)", ev_text)
        en_m = re.search(r"DTEND:([0-9TZ]+)", ev_text)

        if not (loc_m and sum_m and st_m and en_m):
            continue

        location = loc_m.group(1).strip()
        summary = sum_m.group(1).strip()
        desc = desc_m.group(1).strip().replace("\\n", "\n") if desc_m else ""

        # Filter: only laboratory works (location has 'лаба'/'лабораторн' or summary has 📘)
        is_lab = "лаба" in location.lower() or "лабораторн" in location.lower() or "📘" in summary
        if not is_lab:
            continue

        # Parse UTC time and convert to Samara (Europe/Samara, UTC+4)
        try:
            st_utc = datetime.strptime(st_m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            en_utc = datetime.strptime(en_m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        st_sam = st_utc.astimezone(SAMARA_TZ)
        en_sam = en_utc.astimezone(SAMARA_TZ)

        # Clean title
        title_clean = re.sub(r"^[📘📕📗📙\s]+", "", summary).strip()

        # Extract subgroup (1 or 2)
        subgroup = ""
        sg_m = re.search(r"\((\d+)\)", title_clean)
        if sg_m:
            subgroup = sg_m.group(1)
            base_title = re.sub(r"\s*\(\d+\)$", "", title_clean).strip()
        else:
            base_title = title_clean
            if "подгруппа" in desc.lower():
                sg_m2 = re.search(r"подгруппа\s*:\s*(\d+)", desc, re.I)
                if sg_m2:
                    subgroup = sg_m2.group(1)

        base_title = normalize_title(base_title)

        raw_labs.append({
            "base_title": base_title,
            "subgroup": subgroup,
            "location": location,
            "description": desc,
            "start": st_sam,
            "end": en_sam,
            "date": st_sam.date(),
        })

    # Filter by date range: current + next week
    now_samara = datetime.now(SAMARA_TZ).date()
    ref_date = reference_date or now_samara

    # Current week Monday
    monday = ref_date - timedelta(days=ref_date.weekday())
    # Next week Sunday (Monday + 13 days)
    sunday = monday + timedelta(days=13)

    # We only take dates from ref_date (skip past days) up to next week's Sunday
    filtered = [e for e in raw_labs if ref_date <= e["date"] <= sunday]

    # Sort events by date, start time, discipline, subgroup
    filtered.sort(key=lambda x: (x["date"], x["start"], x["base_title"], x["subgroup"]))

    # Merge consecutive pairs:
    # Same date, same base_title, same subgroup, interval between end and next start <= 45 minutes
    merged: List[Dict] = []
    skip_indices = set()

    for i, ev in enumerate(filtered):
        if i in skip_indices:
            continue
        cur = dict(ev)
        for j in range(i + 1, len(filtered)):
            nxt = filtered[j]
            if (
                nxt["date"] == cur["date"]
                and nxt["base_title"].lower() == cur["base_title"].lower()
                and nxt["subgroup"] == cur["subgroup"]
            ):
                diff_minutes = (nxt["start"] - cur["end"]).total_seconds() / 60
                if 0 <= diff_minutes <= 45:
                    cur["end"] = nxt["end"]
                    skip_indices.add(j)
                    break
        merged.append(cur)

    # Format into final laboratory item dictionaries
    results: List[Dict] = []
    for m in merged:
        sg = m["subgroup"]
        sg_str = f" (п/г {sg})" if sg else ""
        subject = f"{m['base_title']}{sg_str}"

        date_iso = m["date"].isoformat()
        d_str = m["start"].strftime("%d.%m.%Y")
        t_start = m["start"].strftime("%H:%M")
        t_end = m["end"].strftime("%H:%M")
        datetime_str = f"{d_str} {t_start} - {t_end}"

        # Clean room and teacher details
        loc_clean = re.sub(r"^лаба\s*/\s*", "", m["location"], flags=re.I).strip()
        lines = [line.strip() for line in m["description"].splitlines() if line.strip()]
        teacher = lines[0] if lines else ""
        desc_parts = []
        if loc_clean:
            desc_parts.append(f"ауд. {loc_clean}")
        if teacher:
            desc_parts.append(f"преп. {teacher}")
        if sg:
            desc_parts.append(f"подгруппа {sg}")
        desc_str = " | ".join(desc_parts)

        # Deterministic external_id
        time_key = m["start"].strftime("%H%M")
        external_id = f"ics:{date_iso}:{subject}:{time_key}"

        results.append({
            "subject": subject,
            "datetime_str": datetime_str,
            "lesson_date": date_iso,
            "description": desc_str,
            "external_id": external_id,
        })

    return results


async def fetch_ics_content(url: str) -> str:
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LabRegisterBot/1.0"
    }
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.text()


async def sync_schedule(
    repo: Repository,
    ics_url: str,
    default_slots: int = 15,
    reference_date: Optional[date] = None,
    system_user_id: int = 0,
) -> Tuple[int, int]:
    """
    Downloads ICS calendar and creates all active laboratory works
    for current + next week.
    Returns (newly_added_count, total_found).
    """
    try:
        content = await fetch_ics_content(ics_url)
    except Exception as e:
        logger.error("Failed to fetch ICS calendar from %s: %s", ics_url, e)
        raise

    labs = parse_and_merge_ics_labs(content, reference_date=reference_date)
    added_count = 0

    for lab in labs:
        created, _ = await repo.sync_external_lesson(
            subject=lab["subject"],
            datetime_str=lab["datetime_str"],
            lesson_date=lab["lesson_date"],
            description=lab["description"],
            max_slots=default_slots,
            created_by=system_user_id,
            external_id=lab["external_id"],
        )
        if created:
            added_count += 1

    logger.info("Schedule sync finished: %d new lessons added out of %d found.", added_count, len(labs))
    return added_count, len(labs)
