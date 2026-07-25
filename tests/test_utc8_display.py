"""Seams for UTC+8 wall-clock display (ADR-0003)."""

from datetime import datetime

import app as app_module
from time_display import format_wall_clock_utc8


def test_format_wall_clock_utc8_shifts_hours():
    utc = datetime(2026, 7, 25, 1, 0, 0)
    assert format_wall_clock_utc8(utc, '%Y-%m-%d %H:%M:%S') == '2026-07-25 09:00:00'


def test_format_wall_clock_utc8_date_uses_utc8_day_boundary():
    # UTC 16:30 on 7/25 → UTC+8 is already 00:30 on 7/26
    utc = datetime(2026, 7, 25, 16, 30, 0)
    assert format_wall_clock_utc8(utc, '%Y-%m-%d') == '2026-07-26'


def test_submissions_list_submitted_at_is_utc8(auth_client):
    ids = auth_client._ids
    quiz_bank_id = ids['quiz_bank_id']
    utc_hand_in = datetime(2026, 7, 25, 16, 30, 0)

    with app_module.app.app_context():
        submission = app_module.Submission(
            student_name='Alice',
            answers='{}',
            score=1,
            total_points=1,
            submitted_at=utc_hand_in,
            quiz_bank_id=quiz_bank_id,
        )
        app_module.db.session.add(submission)
        app_module.db.session.commit()
        submission_id = submission.id

    list_response = auth_client.get(f'/api/quiz-bank/{quiz_bank_id}/submissions')
    assert list_response.status_code == 200
    rows = list_response.get_json()
    match = next(row for row in rows if row['id'] == submission_id)
    assert match['submitted_at'] == '2026-07-26 00:30:00'
