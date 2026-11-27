"""HTTP seam: students answer only inside the Class Session window and while its Course is open.

ADR 0010 and ADR 0011. Windows are relative to the real clock (spec #2 "Testing Decisions").
"""

from datetime import datetime, timedelta

import pytest

import app as app_module
from conftest import make_class_session

LATE_HAND_IN = '課堂已結束，這份作答沒有被收下'


def _html(response):
    return response.get_data(as_text=True)


def _submit(client, code, name='Student A', **extra):
    body = {'student_name': name, 'student_email': '',
            'answers': {str(client._ids['question_id']): 'A'}, 'elapsed_seconds': 95}
    body.update(extra)
    return client.post(f'/api/quiz/{code}/submit', json=body)


def _make_practice():
    with app_module.app.app_context():
        bank = app_module.QuizBank.query.one()
        bank.quiz_mode = 'practice'
        bank.session_question_count = 1
        bank.category_ratios = '{"基礎": 100}'
        for question in bank.questions:
            question.category = '基礎'
        app_module.db.session.commit()


def _submission_count():
    with app_module.app.app_context():
        return app_module.Submission.query.count()


# ---- inside the window ----

def test_live_class_session_code_opens_the_start_page_with_its_time_limit(client):
    code = make_class_session(client._ids, starts_in=-60, ends_in=1800, time_limit=25)
    response = client.get(f'/quiz/{code}')
    assert response.status_code == 200
    html = _html(response)
    assert 'Timed Bank' in html
    assert 'id="student-info-section"' in html
    assert '<b>25</b><span>分鐘</span>' in html  # the Time Limit set by this Class Session
    assert 'const timeLimitMinutes = 25;' in html
    assert '開放到' in html  # green window note


def test_live_practice_class_session_draws_and_plays(client):
    _make_practice()
    code = make_class_session(client._ids)
    assert client.get(f'/quiz/{code}').status_code == 200
    draw = client.post(f'/api/quiz/{code}/draw', json={'student_name': 'Student A'})
    assert draw.status_code == 200, draw.get_json()
    play = client.get(draw.get_json()['redirect'])
    assert play.status_code == 200
    assert 'id="quiz-take"' in _html(play)


def test_hand_in_records_the_class_session_the_quiz_bank_and_the_elapsed_time(client):
    code = make_class_session(client._ids, time_limit=None)
    client.get(f'/quiz/{code}')
    response = _submit(client, code, elapsed_seconds=95)
    assert response.status_code == 200, response.get_json()
    with app_module.app.app_context():
        submission = db_submission(response.get_json()['submission_id'])
        class_session = app_module.ClassSession.query.filter_by(code=code).one()
        assert submission.class_session_id == class_session.id
        assert submission.quiz_bank_id == client._ids['quiz_bank_id']
        assert submission.elapsed_seconds == 95  # stored also without a Time Limit


def db_submission(submission_id):
    return app_module.db.session.get(app_module.Submission, submission_id)


# ---- before the start ----

def test_before_the_start_the_student_sees_the_not_started_page(client):
    code = make_class_session(client._ids, starts_in=3600, ends_in=7200)
    response = client.get(f'/quiz/{code}')
    assert response.status_code == 403
    html = _html(response)
    assert '這堂課還沒開始' in html
    assert 'id="student-info-section"' not in html
    assert 'data-starts-in=' in html  # the countdown that opens the quiz by itself
    assert 'id="quiz-take"' not in _html(client.get(f'/quiz/{code}/play'))


def test_before_the_start_draw_and_hand_in_are_refused(client):
    _make_practice()
    code = make_class_session(client._ids, starts_in=3600, ends_in=7200)
    draw = client.post(f'/api/quiz/{code}/draw', json={'student_name': 'Student A'})
    assert draw.status_code == 403
    assert draw.get_json()['status'] == 'soon'
    assert _submit(client, code).status_code == 403
    assert _submission_count() == 0


# ---- after the end ----

def test_after_the_end_the_start_page_and_play_show_the_ended_page(client):
    code = make_class_session(client._ids, starts_in=-3600, ends_in=-120)
    for path in (f'/quiz/{code}', f'/quiz/{code}/play'):
        response = client.get(path)
        assert response.status_code == 403
        html = _html(response)
        assert '這堂課已經結束' in html
        assert '成績連結' in html  # the Result Link still opens
        assert 'id="quiz-take"' not in html


def test_after_the_end_draw_is_refused(client):
    _make_practice()
    code = make_class_session(client._ids, starts_in=-3600, ends_in=-120)
    draw = client.post(f'/api/quiz/{code}/draw', json={'student_name': 'Student A'})
    assert draw.status_code == 403
    assert draw.get_json()['status'] == 'done'


def test_hand_in_30_seconds_after_the_end_is_accepted(client):
    code = make_class_session(client._ids, starts_in=-3600, ends_in=-30)
    response = _submit(client, code)
    assert response.status_code == 200, response.get_json()
    assert _submission_count() == 1


def test_hand_in_2_minutes_after_the_end_is_refused_and_not_stored(client):
    code = make_class_session(client._ids, starts_in=-3600, ends_in=-120)
    response = _submit(client, code)
    assert response.status_code == 403
    assert response.get_json()['error'] == LATE_HAND_IN
    assert _submission_count() == 0


def test_result_link_still_opens_after_the_class_session_ends(client):
    code = make_class_session(client._ids, starts_in=-3600, ends_in=600)
    result_url = _submit(client, code).get_json()['result_url']
    with app_module.app.app_context():
        class_session = app_module.ClassSession.query.filter_by(code=code).one()
        class_session.ends_at = datetime.utcnow() - timedelta(hours=1)
        app_module.db.session.commit()
    response = client.get(result_url)
    assert response.status_code == 200
    assert 'Timed Bank' in _html(response)


# ---- the Course ----

@pytest.mark.parametrize('course', [
    {'course_ended': True},            # 結束課程 by hand
    {'course_ends_in': -120},          # its end date passed
])
def test_an_ended_course_closes_its_class_sessions(client, course):
    _make_practice()
    code = make_class_session(client._ids, starts_in=-600, ends_in=3000, **course)
    page = client.get(f'/quiz/{code}')
    assert page.status_code == 403
    assert '這堂課已經結束' in _html(page)
    assert client.post(f'/api/quiz/{code}/draw', json={'student_name': 'Student A'}).status_code == 403
    assert '這堂課已經結束' in _html(client.get(f'/quiz/{code}/play'))
    response = _submit(client, code)
    assert response.status_code == 403
    assert response.get_json()['error'] == LATE_HAND_IN
    assert _submission_count() == 0


def test_hand_in_grace_counts_from_the_course_end_when_it_is_earlier(client):
    code = make_class_session(client._ids, starts_in=-600, ends_in=3000, course_ends_in=-30)
    assert _submit(client, code).status_code == 200
    code = make_class_session(client._ids, starts_in=-600, ends_in=3000, course_ends_in=-120, name='另一堂')
    assert _submit(client, code).status_code == 403


def test_a_reopened_course_lets_its_class_sessions_work_again(client):
    _make_practice()
    code = make_class_session(client._ids, starts_in=-600, ends_in=3000, course_ended=True)
    assert client.get(f'/quiz/{code}').status_code == 403
    with app_module.app.app_context():
        app_module.ClassSession.query.filter_by(code=code).one().course.ended_at = None
        app_module.db.session.commit()
    assert client.get(f'/quiz/{code}').status_code == 200
    draw = client.post(f'/api/quiz/{code}/draw', json={'student_name': 'Student A'})
    assert draw.status_code == 200
    assert client.get(draw.get_json()['redirect']).status_code == 200
    assert _submit(client, code).status_code == 200
