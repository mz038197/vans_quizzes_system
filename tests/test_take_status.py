"""HTTP seam: the take page asks the server for the Class Session end during a Take (spec #2 C5, story 90).

GET /api/quiz/<code>/status?bank=<id> gives the effective end (the earlier of the Class Session end
and the Course end) as seconds from now, or ended. The take page polls it, so 結束課程, 立即結束,
延長 and 重新開放 made during a Take reach the student's clock.
"""

from datetime import datetime

import app as app_module
from conftest import make_class_session


def _ids(code):
    with app_module.app.app_context():
        row = app_module.ClassSession.query.filter_by(code=code).one()
        return row.id, row.course_id


def _status(client, code, bank=None):
    bank = client._ids['quiz_bank_id'] if bank is None else bank
    return client.get(f'/api/quiz/{code}/status?bank={bank}')


def test_a_live_class_session_reports_the_seconds_to_its_end(client):
    code = make_class_session(client._ids, starts_in=-600, ends_in=1200)
    response = _status(client, code)
    assert response.status_code == 200
    body = response.get_json()
    assert body['status'] == 'live' and body['ended'] is False
    assert 1190 <= body['ends_in'] <= 1200
    assert len(body['ends_hm']) == 5  # HH:MM in UTC+8


def test_the_course_end_date_cuts_the_end(client):
    code = make_class_session(client._ids, starts_in=-600, ends_in=3000, course_ends_in=600)
    assert 590 <= _status(client, code).get_json()['ends_in'] <= 600


def test_end_now_reports_ended(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=1200)
    session_id, _ = _ids(code)
    assert auth_client.post(f'/api/class-sessions/{session_id}/end', json={}).status_code == 200
    body = _status(auth_client, code).get_json()
    assert body['ended'] is True and body['status'] == 'done' and body['ends_in'] == 0


def test_ending_the_course_reports_ended_and_reopening_it_reports_live_again(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=1200)
    _, course_id = _ids(code)
    assert auth_client.post(f'/api/courses/{course_id}/end', json={}).status_code == 200
    body = _status(auth_client, code).get_json()
    assert body['ended'] is True and body['ends_in'] == 0

    assert auth_client.post(f'/api/courses/{course_id}/reopen', json={}).status_code == 200
    body = _status(auth_client, code).get_json()
    assert body['ended'] is False and body['status'] == 'live'
    assert 1150 <= body['ends_in'] <= 1200


def test_extend_moves_the_reported_end_later(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=600)
    session_id, _ = _ids(code)
    before = _status(auth_client, code).get_json()['ends_in']
    assert auth_client.post(f'/api/class-sessions/{session_id}/extend', json={'minutes': 10}).status_code == 200
    after = _status(auth_client, code).get_json()['ends_in']
    assert 595 <= after - before <= 605


def test_reopen_reports_live_for_30_minutes(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-7200, ends_in=-3600)
    session_id, _ = _ids(code)
    assert _status(auth_client, code).get_json()['ended'] is True
    assert auth_client.post(f'/api/class-sessions/{session_id}/reopen', json={}).status_code == 200
    body = _status(auth_client, code).get_json()
    assert body['ended'] is False and 29 * 60 < body['ends_in'] <= 30 * 60


def test_unknown_code_or_a_quiz_bank_not_offered_is_not_found(client):
    code = make_class_session(client._ids)
    assert client.get('/api/quiz/NOPE99/status').status_code == 404
    assert _status(client, code, bank=999999).status_code == 404


def test_the_take_page_polls_the_status(client):
    code = make_class_session(client._ids)
    html = client.get(f"/quiz/{code}?bank={client._ids['quiz_bank_id']}").get_data(as_text=True)
    assert f'data-status-url="/api/quiz/{code}/status?bank={client._ids["quiz_bank_id"]}"' in html
    assert 'visibilitychange' in html
