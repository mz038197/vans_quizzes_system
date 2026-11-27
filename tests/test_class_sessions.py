"""HTTP seam: open a Class Session for a Quiz Bank inside a Course (ticket 09, issue #11)."""

from datetime import datetime, timedelta

import pytest

import app as app_module
from conftest import OWN_ORIGIN, TEACHER_ROUTER_ID, make_class_session, sign_in, utc8_local


def _open(auth_client, **overrides):
    """POST /api/class-sessions with a valid body; `overrides` replace fields."""
    now = datetime.utcnow()
    body = {
        'new_course_name': '高一 3 班 · 115 上',
        'name': '第 12 週 · 小考',
        'starts_at': utc8_local(now),
        'ends_at': utc8_local(now + timedelta(minutes=50)),
        'banks': [{'quiz_bank_id': auth_client._ids['quiz_bank_id'], 'time_limit_minutes': 20}],
    }
    body.update(overrides)
    return auth_client.post('/api/class-sessions', json=body)


def test_open_class_session_returns_a_code_and_stores_the_offer(auth_client):
    response = _open(auth_client)
    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    code = body['code']
    assert len(code) == 6
    assert body['url'].endswith(f'/quiz/{code}')

    with app_module.app.app_context():
        session_row = app_module.ClassSession.query.filter_by(code=code).one()
        assert session_row.name == '第 12 週 · 小考'
        assert session_row.teacher_id == TEACHER_ROUTER_ID
        assert session_row.course.name == '高一 3 班 · 115 上'
        assert [(o.quiz_bank_id, o.time_limit_minutes) for o in session_row.offers] == [
            (auth_client._ids['quiz_bank_id'], 20)]
        assert round((session_row.ends_at - session_row.starts_at).total_seconds() / 60) == 50


def test_each_class_session_gets_its_own_code(auth_client):
    codes = {_open(auth_client, name=f'第 {n} 堂').get_json()['code'] for n in range(5)}
    assert len(codes) == 5
    for code in codes:
        assert set(code) <= set('ABCDEFGHJKMNPQRSTUVWXYZ23456789')


@pytest.mark.parametrize('overrides, field', [
    ({'name': '  '}, 'name'),
    ({'ends_at': utc8_local(datetime.utcnow() - timedelta(minutes=5)),
      'starts_at': utc8_local(datetime.utcnow() - timedelta(minutes=10))}, 'ends_at'),
    ({'starts_at': utc8_local(datetime.utcnow() + timedelta(hours=2)),
      'ends_at': utc8_local(datetime.utcnow() + timedelta(hours=1))}, 'ends_at'),
    ({'banks': []}, 'banks'),
    ({'new_course_name': ''}, 'course'),
    ({'banks': [{'quiz_bank_id': 0, 'time_limit_minutes': -3}]}, 'banks'),
])
def test_open_class_session_refuses_bad_input(auth_client, overrides, field):
    if overrides.get('banks') and overrides['banks'][0]['quiz_bank_id'] == 0:
        overrides['banks'][0]['quiz_bank_id'] = auth_client._ids['quiz_bank_id']
    response = _open(auth_client, **overrides)
    assert response.status_code == 400
    assert response.get_json()['field'] == field
    assert response.get_json()['error']
    with app_module.app.app_context():
        assert app_module.ClassSession.query.count() == 0
        assert app_module.Course.query.count() == 0


def test_end_not_after_start_and_end_passed_have_their_own_messages(auth_client):
    now = datetime.utcnow()
    same = _open(auth_client, starts_at=utc8_local(now + timedelta(hours=1)), ends_at=utc8_local(now + timedelta(hours=1)))
    assert '晚於開始' in same.get_json()['error']
    passed = _open(auth_client, starts_at=utc8_local(now - timedelta(hours=2)), ends_at=utc8_local(now - timedelta(hours=1)))
    assert '已經過了' in passed.get_json()['error']


def test_open_class_session_in_an_existing_course(auth_client):
    course = auth_client.post('/api/courses', json={'name': '程式社團'})
    assert course.status_code == 201
    course_id = course.get_json()['id']
    response = _open(auth_client, new_course_name=None, course_id=course_id)
    assert response.status_code == 201
    assert response.get_json()['course_id'] == course_id
    with app_module.app.app_context():
        assert app_module.Course.query.count() == 1


def test_an_ended_course_takes_no_new_class_session(auth_client):
    code = make_class_session(auth_client._ids, course_ended=True)
    with app_module.app.app_context():
        course_id = app_module.ClassSession.query.filter_by(code=code).one().course_id
    response = _open(auth_client, new_course_name=None, course_id=course_id)
    assert response.status_code == 400
    assert response.get_json()['field'] == 'course'


def test_a_teacher_opens_class_sessions_only_with_own_quiz_banks_and_courses(client):
    other_code = make_class_session(client._ids, teacher_id=TEACHER_ROUTER_ID + 1)
    with app_module.app.app_context():
        other_course_id = app_module.ClassSession.query.filter_by(code=other_code).one().course_id
    sign_in(client, TEACHER_ROUTER_ID + 1)
    client.environ_base['HTTP_ORIGIN'] = OWN_ORIGIN
    # The fixture Quiz Bank belongs to TEACHER_ROUTER_ID, not to this Teacher.
    assert _open(client).status_code == 404

    sign_in(client, TEACHER_ROUTER_ID)
    response = _open(client, new_course_name=None, course_id=other_course_id)
    assert response.status_code == 404


def test_open_class_session_needs_a_signed_in_teacher_from_this_site(client):
    client.environ_base['HTTP_ORIGIN'] = OWN_ORIGIN
    assert _open(client).status_code == 401
    sign_in(client, TEACHER_ROUTER_ID)
    client.environ_base['HTTP_ORIGIN'] = 'https://evil.example'
    assert _open(client).status_code == 403
