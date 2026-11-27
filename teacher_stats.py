"""Numbers for the Teacher's 儀表板 and 題庫 pages (spec #2).

Plain functions over plain data: app.py runs the queries and passes rows in.
Ticket 13 (#15) adds the Class Session rules (live counts, the 10-minute attention rule) here.
"""

from datetime import timedelta

ATTENTION_BELOW_PERCENT = 60
WEEK = timedelta(days=7)


def submission_percent(score, total_points):
    """Score of one Submission in percent, or None when it has no points."""
    if not total_points:
        return None
    return (score or 0) / total_points * 100


def average_percent(score_pairs):
    """Mean percent over (score, total_points) pairs; None when no pair has points."""
    percents = [p for p in (submission_percent(s, t) for s, t in score_pairs) if p is not None]
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
    """Why a Quiz Bank needs attention, or None. Rule 1: its average is below 60%."""
    if average is not None and average < ATTENTION_BELOW_PERCENT:
        return f'平均 {percent_text(average)}%，低於 {ATTENTION_BELOW_PERCENT}%'
    return None


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
            names.add((name or '').strip())
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
