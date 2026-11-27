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


def random_code():
    return ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def course_end(course):
    """When the Course stops: the earlier of 結束課程 (`ended_at`) and its end date, or None."""
    ends = [t for t in (course.ended_at, course.ends_at) if t is not None]
    return min(ends) if ends else None


def course_is_open(course, now):
    return course.ended_at is None and (course.ends_at is None or now <= course.ends_at)


def effective_end(class_session):
    """The Class Session end as students feel it: its own end, cut at the Course end."""
    end = course_end(class_session.course)
    return class_session.ends_at if end is None else min(class_session.ends_at, end)


def status(class_session, now):
    """SOON before the start, LIVE inside the window, DONE after it or when the Course is not open."""
    if not course_is_open(class_session.course, now):
        return DONE
    if now < class_session.starts_at:
        return SOON
    if now <= class_session.ends_at:
        return LIVE
    return DONE


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


def to_wall_clock(utc_dt):
    """Naive UTC → 'YYYY-MM-DDTHH:MM' in UTC+8, the value a `datetime-local` input takes."""
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(UTC8).strftime('%Y-%m-%dT%H:%M')


def window_text(starts_at, ends_at):
    """'11/27 10:00–10:50' on one day, else '11/27 10:00 – 11/28 10:50' (UTC+8)."""
    start = starts_at.replace(tzinfo=timezone.utc).astimezone(UTC8)
    end = ends_at.replace(tzinfo=timezone.utc).astimezone(UTC8)
    day = lambda t: f'{t.month}/{t.day}'
    if start.date() == end.date():
        return f'{day(start)} {start:%H:%M}–{end:%H:%M}'
    return f'{day(start)} {start:%H:%M} – {day(end)} {end:%H:%M}'
