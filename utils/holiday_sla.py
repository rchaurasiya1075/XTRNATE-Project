"""Holiday calendar + downtime adjustment."""
from datetime import date, datetime, timedelta

import pandas as pd

# National + common festival holidays (India). Extra dates can be passed at runtime.
PUBLIC = {
    date(2025, 1, 26): "Republic Day",
    date(2025, 3, 14): "Holi",
    date(2025, 3, 31): "Eid-ul-Fitr",
    date(2025, 4, 10): "Mahavir Jayanti",
    date(2025, 4, 18): "Good Friday",
    date(2025, 4, 14): "Ambedkar Jayanti",
    date(2025, 5, 1): "Labour Day",
    date(2025, 6, 7): "Eid-ul-Adha",
    date(2025, 8, 15): "Independence Day",
    date(2025, 8, 16): "Janmashtami",
    date(2025, 10, 2): "Gandhi Jayanti",
    date(2025, 10, 2): "Gandhi Jayanti",
    date(2025, 10, 20): "Dussehra",
    date(2025, 10, 21): "Diwali",
    date(2025, 10, 22): "Govardhan Puja",
    date(2025, 12, 25): "Christmas",
    date(2026, 1, 26): "Republic Day",
    date(2026, 3, 3): "Holi",
    date(2026, 3, 21): "Eid-ul-Fitr",
    date(2026, 3, 31): "Ram Navami",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Ambedkar Jayanti",
    date(2026, 5, 1): "Labour Day",
    date(2026, 5, 27): "Eid-ul-Adha",
    date(2026, 8, 15): "Independence Day",
    date(2026, 9, 4): "Janmashtami",
    date(2026, 10, 2): "Gandhi Jayanti",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 8): "Diwali",
    date(2026, 11, 9): "Govardhan Puja",
    date(2026, 12, 25): "Christmas",
}


def nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    d += timedelta(weeks=n - 1)
    return d if d.month == month else None


def holiday_label(d, extra=None):
    extra = extra or {}
    if d in extra:
        return extra[d]
    if d in PUBLIC:
        return PUBLIC[d]
    if d.weekday() == 6:
        return "Sunday"
    sat2 = nth_weekday(d.year, d.month, 5, 2)
    sat4 = nth_weekday(d.year, d.month, 5, 4)
    if sat2 and d == sat2:
        return "2nd Saturday"
    if sat4 and d == sat4:
        return "4th Saturday"
    return None


def overlap_minutes(start, end, day):
    day_start = datetime.combine(day, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    a = max(start, day_start)
    b = min(end, day_end)
    if b <= a:
        return 0
    return int((b - a).total_seconds() // 60)


def adjust_ticket(submitted, resolved, reported_min, extra=None):
    extra = extra or {}
    if pd.isna(submitted) or pd.isna(resolved):
        raw = int(reported_min) if pd.notna(reported_min) else 0
        return {
            "raw_min": raw,
            "holiday_min": 0,
            "adj_min": raw,
            "why": "Submitted / Resolved missing — holiday minus nahi nikala",
            "holiday_days": "",
        }
    start = pd.Timestamp(submitted).to_pydatetime().replace(tzinfo=None)
    end = pd.Timestamp(resolved).to_pydatetime().replace(tzinfo=None)
    if end < start:
        start, end = end, start
    span = int((end - start).total_seconds() // 60)
    raw = int(reported_min) if pd.notna(reported_min) else span
    # Prefer reported downtime if present, else clock span
    if pd.notna(reported_min):
        raw = int(round(float(reported_min)))

    pieces = []
    hmin = 0
    day = start.date()
    last = end.date()
    while day <= last:
        lab = holiday_label(day, extra)
        if lab:
            mins = overlap_minutes(start, end, day)
            if mins > 0:
                hmin += mins
                pieces.append(f"{lab} {day.strftime('%d-%b-%Y')} ({mins} min)")
        day += timedelta(days=1)

    # Holiday cannot exceed raw
    hmin = min(hmin, max(raw, 0))
    adj = max(raw - hmin, 0)
    if hmin == 0:
        why = "Is ticket ke Submitted→Resolved window mein Sunday / 2nd-4th Sat / public holiday overlap nahi. Reported DT same rakha."
    else:
        why = (
            f"Reported / clock DT {raw} min. Holiday overlap {hmin} min minus kiya "
            f"kyunki outage in days pe pada: {'; '.join(pieces)}. "
            f"Billable / working DT = {adj} min ({round(adj/60, 2)} hrs)."
        )
    return {
        "raw_min": raw,
        "holiday_min": hmin,
        "adj_min": adj,
        "why": why,
        "holiday_days": "; ".join(pieces),
    }


def parse_extra_dates(text):
    extra = {}
    if not text:
        return extra
    for line in str(text).splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.replace(",", " ").split() if p.strip()]
        # YYYY-MM-DD Name...
        try:
            d = datetime.strptime(parts[0], "%Y-%m-%d").date()
            extra[d] = " ".join(parts[1:]) or "Extra Holiday"
        except Exception:
            continue
    return extra
