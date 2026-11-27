"""HTTP seam: the start and take pages get the Time Limit and the Class Session end (ticket 12, #14).

The page runs both clocks in the browser (ADR 0001). These tests check what the server sends:
the Time Limit of this Quiz Bank in this Class Session, and the effective Class Session end
(the earlier of the Class Session end and the Course end) as seconds left and as a UTC+8 wall clock.
The clocks themselves are checked by hand in a browser (spec #2 "Testing Decisions").
"""

import re
from datetime import datetime, timedelta, timezone

import app as app_module
from conftest import make_class_session


def _html(response):
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _take_attr(html, name):
    match = re.search(r'<div class="qz-take" id="quiz-take"[^>]*\b' + name + r'="([^"]*)"', html)
    assert match, f'{name} missing on #quiz-take'
    return match.group(1)


def _utc8_hm(seconds_from_now):
    end = datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now)
    return end.astimezone(timezone(timedelta(hours=8))).strftime('%H:%M')


def _close_to(value, expected, slack=5):
    return expected - slack <= int(value) <= expected


def _make_practice():
    with app_module.app.app_context():
        bank = app_module.QuizBank.query.one()
        bank.quiz_mode = 'practice'
        bank.session_question_count = 1
        bank.category_ratios = '{"基礎": 100}'
        for question in bank.questions:
            question.category = '基礎'
        app_module.db.session.commit()


# ---- what the take page receives ----

def test_take_page_gets_the_time_limit_and_the_class_session_end(client):
    code = make_class_session(client._ids, ends_in=1800, time_limit=20)
    html = _html(client.get(f'/quiz/{code}'))
    assert _take_attr(html, 'data-time-limit') == '20'
    assert _close_to(_take_attr(html, 'data-session-ends-in'), 1800)
    assert _take_attr(html, 'data-session-end-hm') in {_utc8_hm(1800), _utc8_hm(1795)}


def test_take_page_without_a_time_limit_has_an_empty_limit_and_still_the_end(client):
    code = make_class_session(client._ids, ends_in=1800, time_limit=None)
    html = _html(client.get(f'/quiz/{code}'))
    assert _take_attr(html, 'data-time-limit') == ''
    assert _close_to(_take_attr(html, 'data-session-ends-in'), 1800)
    assert '已作答時間' in html


def test_the_course_end_cuts_the_class_session_end_sent_to_the_page(client):
    code = make_class_session(client._ids, ends_in=3600, time_limit=20, course_ends_in=600)
    html = _html(client.get(f'/quiz/{code}'))
    assert _close_to(_take_attr(html, 'data-session-ends-in'), 600)
    assert _take_attr(html, 'data-session-end-hm') in {_utc8_hm(600), _utc8_hm(595)}


def test_practice_play_page_gets_the_time_limit_and_the_end(client):
    _make_practice()
    code = make_class_session(client._ids, ends_in=1800, time_limit=15, course_ends_in=900)
    draw = client.post(f'/api/quiz/{code}/draw',
                       json={'student_name': 'Student A', 'quiz_bank_id': client._ids['quiz_bank_id']})
    assert draw.status_code == 200
    html = _html(client.get(draw.get_json()['redirect']))
    assert _take_attr(html, 'data-time-limit') == '15'
    assert _close_to(_take_attr(html, 'data-session-ends-in'), 900)


# ---- start page warning: less Class Session time left than the Time Limit ----

SHORT_WARNING = re.compile(r'課堂只剩 (\d+) 分鐘，比作答時限短，(\d\d:\d\d) 會自動交卷')


def test_start_page_warns_when_the_class_session_ends_before_the_time_limit(client):
    code = make_class_session(client._ids, ends_in=8 * 60 + 30, time_limit=20)
    html = _html(client.get(f'/quiz/{code}'))
    match = SHORT_WARNING.search(html)
    assert match, 'warning missing'
    assert match.group(1) == '8'
    assert match.group(2) in {_utc8_hm(8 * 60 + 30), _utc8_hm(8 * 60 + 25)}
    assert 'id="start-btn"' in html  # the warning does not block the start


def test_start_page_warning_uses_the_course_end(client):
    code = make_class_session(client._ids, ends_in=3600, time_limit=20, course_ends_in=5 * 60 + 30)
    match = SHORT_WARNING.search(_html(client.get(f'/quiz/{code}')))
    assert match and match.group(1) == '5'


def test_practice_start_page_warns_too(client):
    _make_practice()
    code = make_class_session(client._ids, ends_in=10 * 60 + 30, time_limit=30)
    match = SHORT_WARNING.search(_html(client.get(f'/quiz/{code}')))
    assert match and match.group(1) == '10'


def test_no_warning_when_the_time_limit_fits_in_the_class_session(client):
    code = make_class_session(client._ids, ends_in=1800, time_limit=20)
    assert not SHORT_WARNING.search(_html(client.get(f'/quiz/{code}')))


def test_no_warning_without_a_time_limit(client):
    code = make_class_session(client._ids, ends_in=120, time_limit=None)
    assert not SHORT_WARNING.search(_html(client.get(f'/quiz/{code}')))


# ---- Elapsed Time is stored also without a Time Limit ----

def test_untimed_class_session_submission_records_the_elapsed_time(client):
    code = make_class_session(client._ids, time_limit=None)
    response = client.post(f'/api/quiz/{code}/submit', json={
        'student_name': 'Student A', 'student_email': '',
        'answers': {str(client._ids['question_id']): 'A'},
        'quiz_bank_id': client._ids['quiz_bank_id'], 'elapsed_seconds': 321,
    })
    assert response.status_code == 200
    with app_module.app.app_context():
        submission = app_module.Submission.query.one()
        assert submission.elapsed_seconds == 321
        assert submission.class_session.code == code
