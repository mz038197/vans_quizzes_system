"""HTTP seam: Courses: create, rename, end date, end, reopen, delete (ticket 11, issue #13; ADR 0011)."""

from datetime import datetime, timedelta, timezone

import app as app_module
from conftest import OWN_ORIGIN, TEACHER_ROUTER_ID, make_class_session, utc8_local

UTC8 = timezone(timedelta(hours=8))


def _utc8_day(days_from_today):
    return (datetime.now(UTC8) + timedelta(days=days_from_today)).strftime('%Y-%m-%d')


def _course(course_id):
    with app_module.app.app_context():
        return app_module.db.session.get(app_module.Course, course_id)


def _course_of(code):
    with app_module.app.app_context():
        return app_module.ClassSession.query.filter_by(code=code).one().course_id


def _hand_in(client, code):
    ids = client._ids
    response = client.post(f'/api/quiz/{code}/submit', json={
        'student_name': 'Student A', 'answers': {str(ids['question_id']): 'A'},
        'elapsed_seconds': 10, 'quiz_bank_id': ids['quiz_bank_id']})
    assert response.status_code == 200, response.get_json()


def test_create_a_course_with_an_end_date_stored_as_2359_utc8(auth_client):
    day = _utc8_day(30)
    response = auth_client.post('/api/courses', json={'name': '高一 3 班 · 115 上', 'ends_on': day})
    assert response.status_code == 201, response.get_json()
    course = _course(response.get_json()['id'])
    assert course.name == '高一 3 班 · 115 上'
    assert course.teacher_id == TEACHER_ROUTER_ID
    local = course.ends_at.replace(tzinfo=timezone.utc).astimezone(UTC8)
    assert local.strftime('%Y-%m-%d %H:%M') == f'{day} 23:59'
    assert course.ended_at is None


def test_create_a_course_without_an_end_date(auth_client):
    response = auth_client.post('/api/courses', json={'name': '程式社團', 'ends_on': ''})
    assert response.status_code == 201
    assert _course(response.get_json()['id']).ends_at is None


def test_a_past_end_date_is_refused(auth_client):
    response = auth_client.post('/api/courses', json={'name': '舊課', 'ends_on': _utc8_day(-1)})
    assert response.status_code == 400
    assert response.get_json()['field'] == 'ends_on'
    course_id = auth_client.post('/api/courses', json={'name': '新課'}).get_json()['id']
    response = auth_client.put(f'/api/courses/{course_id}', json={'name': '新課', 'ends_on': _utc8_day(-3)})
    assert response.status_code == 400
    assert response.get_json()['field'] == 'ends_on'


def test_today_is_not_a_past_end_date(auth_client):
    response = auth_client.post('/api/courses', json={'name': '今天結束', 'ends_on': _utc8_day(0)})
    assert response.status_code == 201


def test_rename_and_change_or_clear_the_end_date(auth_client):
    course_id = auth_client.post('/api/courses', json={'name': '舊名'}).get_json()['id']
    response = auth_client.put(f'/api/courses/{course_id}', json={'name': '新名', 'ends_on': _utc8_day(10)})
    assert response.status_code == 200, response.get_json()
    assert _course(course_id).name == '新名'
    assert _course(course_id).ends_at is not None
    response = auth_client.put(f'/api/courses/{course_id}', json={'name': '新名', 'ends_on': None})
    assert response.status_code == 200
    assert _course(course_id).ends_at is None


def test_rename_refuses_an_empty_name(auth_client):
    course_id = auth_client.post('/api/courses', json={'name': '舊名'}).get_json()['id']
    response = auth_client.put(f'/api/courses/{course_id}', json={'name': '  '})
    assert response.status_code == 400
    assert response.get_json()['field'] == 'name'


def test_end_course_ends_its_class_sessions_without_changing_their_times(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=2400)
    course_id = _course_of(code)
    with app_module.app.app_context():
        before = app_module.ClassSession.query.filter_by(code=code).one().ends_at
    response = auth_client.post(f'/api/courses/{course_id}/end')
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['n_ended'] == 1
    assert _course(course_id).ended_at is not None
    with app_module.app.app_context():
        assert app_module.ClassSession.query.filter_by(code=code).one().ends_at == before
    assert auth_client.get(f'/quiz/{code}').status_code == 403


def test_reopen_brings_back_class_sessions_whose_end_is_ahead(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=2400, course_ended=True)
    course_id = _course_of(code)
    assert auth_client.get(f'/quiz/{code}').status_code == 403
    response = auth_client.post(f'/api/courses/{course_id}/reopen')
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['n_back'] == 1
    assert _course(course_id).ended_at is None
    assert auth_client.get(f'/quiz/{code}').status_code == 200


def test_reopen_clears_an_end_date_that_has_passed(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=2400, course_ends_in=-120)
    course_id = _course_of(code)
    response = auth_client.post(f'/api/courses/{course_id}/reopen')
    assert response.status_code == 200
    assert _course(course_id).ends_at is None
    assert auth_client.get(f'/quiz/{code}').status_code == 200


def test_an_ended_course_refuses_new_class_sessions(auth_client):
    code = make_class_session(auth_client._ids, course_ended=True)
    now = datetime.utcnow()
    response = auth_client.post('/api/class-sessions', json={
        'course_id': _course_of(code), 'name': '再一堂',
        'starts_at': utc8_local(now), 'ends_at': utc8_local(now + timedelta(minutes=50)),
        'banks': [{'quiz_bank_id': auth_client._ids['quiz_bank_id']}]})
    assert response.status_code == 400
    assert response.get_json()['field'] == 'course'


def test_an_ended_course_refuses_start_now_extend_and_reopen(auth_client):
    ids = auth_client._ids
    for starts_in, ends_in, action in [(3600, 7200, 'start-now'), (-600, 2400, 'extend'), (-7200, -3600, 'reopen')]:
        code = make_class_session(ids, starts_in=starts_in, ends_in=ends_in, course_ended=True)
        with app_module.app.app_context():
            session_id = app_module.ClassSession.query.filter_by(code=code).one().id
        response = auth_client.post(f'/api/class-sessions/{session_id}/{action}', json={})
        assert response.status_code == 400, action
        assert response.get_json()['field'] == 'course'


def test_delete_a_course_without_submissions(auth_client):
    code = make_class_session(auth_client._ids)
    course_id = _course_of(code)
    response = auth_client.delete(f'/api/courses/{course_id}', json={})
    assert response.status_code == 200
    with app_module.app.app_context():
        assert app_module.db.session.get(app_module.Course, course_id) is None
        assert app_module.ClassSession.query.count() == 0


def test_delete_a_course_with_submissions_needs_the_confirm_flag(auth_client):
    code = make_class_session(auth_client._ids)
    _hand_in(auth_client, code)
    course_id = _course_of(code)
    refused = auth_client.delete(f'/api/courses/{course_id}', json={})
    assert refused.status_code == 409
    assert refused.get_json()['session_count'] == 1
    assert refused.get_json()['submission_count'] == 1

    response = auth_client.delete(f'/api/courses/{course_id}', json={'confirm': True})
    assert response.status_code == 200
    with app_module.app.app_context():
        assert app_module.ClassSession.query.count() == 0
        assert app_module.Submission.query.count() == 0
        assert app_module.QuizBank.query.count() == 1  # Quiz Banks stay


def test_another_teachers_course_cannot_be_changed(auth_client):
    code = make_class_session(auth_client._ids, teacher_id=TEACHER_ROUTER_ID + 1)
    course_id = _course_of(code)
    assert auth_client.put(f'/api/courses/{course_id}', json={'name': 'x'}).status_code == 404
    assert auth_client.post(f'/api/courses/{course_id}/end').status_code == 404
    assert auth_client.post(f'/api/courses/{course_id}/reopen').status_code == 404
    assert auth_client.delete(f'/api/courses/{course_id}', json={'confirm': True}).status_code == 404
    assert _course(course_id).name == '測試課堂 的課程'


def test_course_writes_need_a_signed_in_teacher(client):
    client.environ_base['HTTP_ORIGIN'] = OWN_ORIGIN
    code = make_class_session(client._ids)
    course_id = _course_of(code)
    assert client.post('/api/courses', json={'name': 'x'}).status_code == 401
    assert client.post(f'/api/courses/{course_id}/end').status_code == 401
