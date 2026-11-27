"""Time rules for Courses and Class Sessions (ADR 0010, ADR 0011). No database access here.

All datetimes are naive UTC, as stored. `course` and `class_session` are any objects with the
model attributes (`ended_at`, `ends_at`; `starts_at`, `ends_at`, `course`).
"""

import secrets
from datetime import datetime, timedelta, timezone

# 6 characters a student can read aloud: no 0/O, 1/I/L look-alikes.
CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
CODE_LENGTH = 6

# A hand-in is accepted up to this long after the effective end (spec #2 "Window check").
HAND_IN_GRACE = timedelta(seconds=60)

UTC8 = timezone(timedelta(hours=8))

# Status keys, also used by the `ui.status_pill` macro and the `.sp.<status>` CSS.
SOON, LIVE, DONE = 'soon', 'live', 'done'
# The order in which lists show Class Sessions: live, then upcoming, then ended.
STATUS_ORDER = (LIVE, SOON, DONE)


def random_code():
    return ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def course_end(course):
    """When the Course stops: the earlier of 結束課程 (`ended_at`) and its end date, or None."""
    ends = [t for t in (course.ended_at, course.ends_at) if t is not None]
    return min(ends) if ends else None


def course_is_open(course, now):
    return course.ended_at is None and (course.ends_at is None or now <= course.ends_at)


def parse_course_end(value, now):
    """A Course end date ('YYYY-MM-DD', a UTC+8 day) → naive UTC of 23:59 that day.

    Returns (ends_at or None, error or None). Empty means no end date. A day already past is refused (spec #2).
    """
    if value is None or not str(value).strip():
        return None, None
    try:
        day = datetime.strptime(str(value).strip()[:10], '%Y-%m-%d')
    except ValueError:
        return None, '結束日期的格式不對'
    ends_at = parse_wall_clock(day.replace(hour=23, minute=59).isoformat())
    if ends_at < now:
        return None, '結束日期已經過了。要結束課程，請按「結束課程」。'
    return ends_at, None


def course_end_text(course, now):
    """到 12/31 23:59 / 已在 11/27 結束 / 沒有結束日期 (UTC+8)."""
    if not course_is_open(course, now):
        return f'已在 {month_day(course_end(course))} 結束'
    if course.ends_at is not None:
        return f'到 {month_day(course.ends_at)} 23:59'
    return '沒有結束日期'


def effective_end(class_session):
    """The Class Session end as students feel it: its own end, cut at the Course end."""
    end = course_end(class_session.course)
    return class_session.ends_at if end is None else min(class_session.ends_at, end)


def has_started(class_session, now):
    """After the start, the start time and the Time Limits already offered are fixed (spec #2)."""
    return now >= class_session.starts_at


def status(class_session, now):
    """SOON before the start, LIVE inside the window, DONE after it or when the Course is not open."""
    if not course_is_open(class_session.course, now):
        return DONE
    if now < class_session.starts_at:
        return SOON
    if now <= class_session.ends_at:
        return LIVE
    return DONE


def list_order(class_session, status_now):
    """Sort key for a list of Class Sessions: live, then upcoming (soonest start first),
    then ended (latest effective end first). `status_now` is status(class_session, now)."""
    rank = STATUS_ORDER.index(status_now)
    if status_now == DONE:
        return (rank, -effective_end(class_session).timestamp())
    return (rank, class_session.starts_at.timestamp())


def accepts_hand_in(class_session, now):
    """A hand-in counts when the Take could have started and it arrives within the grace after the end."""
    return class_session.starts_at <= now <= effective_end(class_session) + HAND_IN_GRACE


def parse_wall_clock(value):
    """Read an ISO 8601 time from the browser as naive UTC.

    A time without an offset is a UTC+8 wall clock (ADR 0003), which is what a
    `datetime-local` input gives. Returns None when the text is not a time.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC8)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)


def to_utc8(utc_dt):
    """Naive UTC → an aware UTC+8 datetime (ADR 0003)."""
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(UTC8)


def to_wall_clock(utc_dt):
    """Naive UTC → 'YYYY-MM-DDTHH:MM' in UTC+8, the value a `datetime-local` input takes."""
    return to_utc8(utc_dt).strftime('%Y-%m-%dT%H:%M')


def month_day(utc_dt):
    """Naive UTC → '11/27', the UTC+8 day."""
    local = to_utc8(utc_dt)
    return f'{local.month}/{local.day}'


def window_text(starts_at, ends_at):
    """'11/27 10:00–10:50' on one day, else '11/27 10:00 – 11/28 10:50' (UTC+8)."""
    start, end = to_utc8(starts_at), to_utc8(ends_at)
    if start.date() == end.date():
        return f'{month_day(starts_at)} {start:%H:%M}–{end:%H:%M}'
    return f'{month_day(starts_at)} {start:%H:%M} – {month_day(ends_at)} {end:%H:%M}'
