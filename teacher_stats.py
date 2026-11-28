"""Numbers for the Teacher's 儀表板 and 題庫 pages (spec #2).

Plain functions over plain data: app.py runs the queries and passes rows in.
Class Session statuses come from class_session_rules.status (an ended Course makes them DONE).
"""

from datetime import timedelta, timezone

import grade_stats
from class_session_rules import LIVE, SOON, UTC8

ATTENTION_BELOW_PERCENT = grade_stats.PASS_PERCENT
WEEK = timedelta(days=7)


def submission_percent(score, total_points):
    """grade_stats.percent, but None when the Submission has no points: the dashboard shows — for it
    and leaves it out of averages (grade_stats.percent gives 0)."""
    return grade_stats.percent(score, total_points) if total_points else None


def average_percent(score_pairs):
    """Mean percent over (score, total_points) pairs; None when no pair has points."""
    percents = [grade_stats.percent(s, t) for s, t in score_pairs if t]
    if not percents:
        return None
    return sum(percents) / len(percents)


def percent_text(value):
    """Whole percent for display; one decimal when rounding would hide that it is below 60."""
    text = f'{value:.0f}'
    if value < ATTENTION_BELOW_PERCENT and int(text) >= ATTENTION_BELOW_PERCENT:
        text = f'{value:.1f}'
    return text


def attention_reason(average):
    """Why a Quiz Bank needs attention, or None: its average is below 60%.

    A live Class Session with no Submission yet is not a reason: a Class Session can run for hours.
    """
    if average is not None and average < ATTENTION_BELOW_PERCENT:
        return f'平均 {percent_text(average)}%，低於 {ATTENTION_BELOW_PERCENT}%'
    return None


def wall_clock_text(utc_dt):
    """'11/28 10:00' in UTC+8."""
    t = utc_dt.replace(tzinfo=timezone.utc).astimezone(UTC8)
    return f'{t.month}/{t.day} {t:%H:%M}'


def duration_text(delta):
    """A rough length for 剩 … / … 後: minutes, then hours, then days."""
    minutes = max(0, round(delta.total_seconds() / 60))
    if minutes < 60:
        return f'{minutes} 分鐘'
    hours = round(minutes / 60)
    if hours < 48:
        return f'{hours} 小時'
    return f'{round(hours / 24)} 天'


def bank_session_status(sessions):
    """The Class Session status of one Quiz Bank: (kind, text).

    `sessions` is an iterable of (status, starts_at). kind is 'live', 'soon' or 'none'.
    """
    sessions = list(sessions)
    live = sum(1 for status, _ in sessions if status == LIVE)
    if live:
        return 'live', f'● {live} 堂進行中'
    upcoming = sorted(starts_at for status, starts_at in sessions if status == SOON)
    if upcoming:
        return 'soon', f'下一堂 {wall_clock_text(upcoming[0])}'
    return 'none', '沒有課堂'


def week_numbers(hand_ins, now):
    """Submissions in the last 7 days, in the 7 days before, and distinct trimmed names this week.

    `hand_ins` is an iterable of (student_name, submitted_at) in UTC.
    """
    week_start = now - WEEK
    last_week_start = week_start - WEEK
    week_subs = 0
    last_week_subs = 0
    names = set()
    for name, submitted_at in hand_ins:
        if submitted_at is None:
            continue
        if submitted_at >= week_start:
            week_subs += 1
            names.add(grade_stats.trimmed_name(name))
        elif submitted_at >= last_week_start:
            last_week_subs += 1
    return {
        'week_subs': week_subs,
        'last_week_subs': last_week_subs,
        'week_delta': week_subs - last_week_subs,
        'week_students': len(names),
    }


def delta_text(delta):
    if delta > 0:
        return f'比上週 +{delta}'
    if delta < 0:
        return f'比上週 {delta}'
    return '和上週持平'
