"""Numbers for the Quiz Bank 成績 page (spec #2 "Grades", ticket 15 / #17).

Plain functions over plain data: app.py runs the queries and passes rows in.
"""

PASS_PERCENT = 60
BANDS = (('90–100', 90), ('80–89', 80), ('70–79', 70), ('60–69', 60), ('0–59', 0))
MOST_MISSED_LIMIT = 5


def percent(score, total_points):
    """Score of one Submission in percent; 0 when it has no points."""
    if not total_points:
        return 0.0
    return (score or 0) / total_points * 100


def trimmed_name(name):
    """Names match after trimming spaces (spec #2 user story 110)."""
    return (name or '').strip()


def summary(percents, names):
    """The four KPI numbers: count, distinct trimmed names, average, median, highest, lowest, pass rate."""
    values = sorted(percents)
    count = len(values)
    if not count:
        return {'count': 0, 'students': 0, 'average': None, 'median': None,
                'highest': None, 'lowest': None, 'passed': 0, 'pass_rate': None}
    middle = count // 2
    median = values[middle] if count % 2 else (values[middle - 1] + values[middle]) / 2
    passed = sum(1 for p in values if p >= PASS_PERCENT)
    return {
        'count': count,
        'students': len({trimmed_name(n) for n in names}),
        'average': sum(values) / count,
        'median': median,
        'highest': values[-1],
        'lowest': values[0],
        'passed': passed,
        'pass_rate': passed / count * 100,
    }


def bands(percents):
    """Counts in the five score bands, highest band first."""
    counts = [0] * len(BANDS)
    for p in percents:
        for i, (_, floor) in enumerate(BANDS):
            if p >= floor:
                counts[i] += 1
                break
    return [{'label': label, 'count': c} for (label, _), c in zip(BANDS, counts)]


def take_numbers(hand_ins):
    """Repeat-Take numbers per (trimmed name, Class Session, Quiz Bank) in hand-in order.

    `hand_ins`: iterable of (id, name, class_session_id, quiz_bank_id, submitted_at).
    Returns {id: (take, takes)}.
    """
    groups = {}
    for sub_id, name, class_session_id, quiz_bank_id, submitted_at in hand_ins:
        key = (trimmed_name(name), class_session_id, quiz_bank_id)
        groups.setdefault(key, []).append((submitted_at, sub_id))
    numbers = {}
    for members in groups.values():
        members.sort()
        for n, (_, sub_id) in enumerate(members, start=1):
            numbers[sub_id] = (n, len(members))
    return numbers


def is_time_up(elapsed_seconds, time_limit_minutes):
    """A Take hit its Time Limit when its Elapsed Time reached the limit."""
    if not time_limit_minutes or elapsed_seconds is None:
        return False
    return elapsed_seconds >= time_limit_minutes * 60


def most_missed(judgements, limit=MOST_MISSED_LIMIT):
    """The questions most often answered wrong.

    `judgements`: iterable of (question_id, is_right), one per question per Submission.
    Returns [{question_id, wrong, seen, wrong_rate}] with at least one wrong answer,
    highest wrong rate first (then more wrong answers first).
    """
    seen = {}
    wrong = {}
    for question_id, is_right in judgements:
        seen[question_id] = seen.get(question_id, 0) + 1
        if not is_right:
            wrong[question_id] = wrong.get(question_id, 0) + 1
    rows = [{'question_id': q, 'wrong': w, 'seen': seen[q], 'wrong_rate': w / seen[q] * 100}
            for q, w in wrong.items()]
    rows.sort(key=lambda r: (-r['wrong_rate'], -r['wrong']))
    return rows[:limit]


def elapsed_text(elapsed_seconds):
    """Elapsed Time as m:ss; empty when unknown."""
    if elapsed_seconds is None:
        return ''
    return f'{elapsed_seconds // 60}:{elapsed_seconds % 60:02d}'
