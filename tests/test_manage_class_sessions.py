"""HTTP seam: edit, end, start, extend, reopen and delete a Class Session (ticket 11, issue #13)."""

from datetime import datetime, timedelta

import app as app_module
from conftest import TEACHER_ROUTER_ID, make_class_session, sign_in, utc8_local


def _session(code):
    with app_module.app.app_context():
        row = app_module.ClassSession.query.filter_by(code=code).one()
        return {
            'id': row.id, 'name': row.name, 'starts_at': row.starts_at, 'ends_at': row.ends_at,
            'banks': [(o.quiz_bank_id, o.time_limit_minutes) for o in row.offers],
        }


def _edit_body(code, **overrides):
    row = _session(code)
    body = {
        'name': row['name'],
        'starts_at': utc8_local(row['starts_at']),
        'ends_at': utc8_local(row['ends_at']),
        'banks': [{'quiz_bank_id': b, 'time_limit_minutes': t} for b, t in row['banks']],
    }
    body.update(overrides)
    return row['id'], body


def _second_bank(title='第二份題庫'):
    with app_module.app.app_context():
        bank = app_module.QuizBank(title=title, description='',
                                   teacher_id=TEACHER_ROUTER_ID, quiz_mode='fixed')
        app_module.db.session.add(bank)
        app_module.db.session.flush()
        question = app_module.Question(title='Q', question_text='?', question_type='single_choice',
                                       question_data='{"options": ["A", "B"], "correct_answer": "A"}',
                                       points=1, order_index=0, quiz_bank_id=bank.id)
        app_module.db.session.add(question)
        app_module.db.session.commit()
        return bank.id, question.id


def _offer(code, bank_id, time_limit=None):
    with app_module.app.app_context():
        row = app_module.ClassSession.query.filter_by(code=code).one()
        app_module.db.session.add(app_module.ClassSessionBank(
            class_session_id=row.id, quiz_bank_id=bank_id, position=len(row.offers), time_limit_minutes=time_limit))
        app_module.db.session.commit()


def _hand_in(client, code, bank_id, question_id, name='Student A'):
    response = client.post(f'/api/quiz/{code}/submit', json={
        'student_name': name, 'answers': {str(question_id): 'A'}, 'elapsed_seconds': 10, 'quiz_bank_id': bank_id})
    assert response.status_code == 200, response.get_json()


def _count_submissions(code):
    with app_module.app.app_context():
        row = app_module.ClassSession.query.filter_by(code=code).first()
        return app_module.Submission.query.filter_by(class_session_id=row.id).count() if row else None


# ---- edit ----

def test_before_the_start_the_start_and_time_limits_can_change(auth_client):
    code = make_class_session(auth_client._ids, starts_in=3600, ends_in=7200, time_limit=20)
    new_start = datetime.utcnow() + timedelta(hours=3)
    session_id, body = _edit_body(code, starts_at=utc8_local(new_start), ends_at=utc8_local(new_start + timedelta(minutes=45)),
                                  banks=[{'quiz_bank_id': auth_client._ids['quiz_bank_id'], 'time_limit_minutes': 35}])
    response = auth_client.put(f'/api/class-sessions/{session_id}', json=body)
    assert response.status_code == 200, response.get_json()
    row = _session(code)
    assert abs((row['starts_at'] - new_start).total_seconds()) < 2
    assert row['banks'] == [(auth_client._ids['quiz_bank_id'], 35)]


def test_after_the_start_changing_the_start_is_refused(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=2400)
    session_id, body = _edit_body(code, starts_at=utc8_local(datetime.utcnow() + timedelta(minutes=5)))
    response = auth_client.put(f'/api/class-sessions/{session_id}', json=body)
    assert response.status_code == 400
    assert response.get_json()['field'] == 'starts_at'


def test_after_the_start_changing_a_time_limit_is_refused(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=2400, time_limit=20)
    session_id, body = _edit_body(code, banks=[{'quiz_bank_id': auth_client._ids['quiz_bank_id'], 'time_limit_minutes': 40}])
    response = auth_client.put(f'/api/class-sessions/{session_id}', json=body)
    assert response.status_code == 400
    assert response.get_json()['field'] == 'banks'
    assert _session(code)['banks'] == [(auth_client._ids['quiz_bank_id'], 20)]


def test_after_the_start_the_name_end_and_banks_can_change(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=2400, time_limit=20)
    bank_id, _ = _second_bank()
    new_end = datetime.utcnow() + timedelta(hours=2)
    session_id, body = _edit_body(code, name='改過的名字', ends_at=utc8_local(new_end), banks=[
        {'quiz_bank_id': auth_client._ids['quiz_bank_id'], 'time_limit_minutes': 20},
        {'quiz_bank_id': bank_id, 'time_limit_minutes': 15},
    ])
    response = auth_client.put(f'/api/class-sessions/{session_id}', json=body)
    assert response.status_code == 200, response.get_json()
    row = _session(code)
    assert row['name'] == '改過的名字'
    assert abs((row['ends_at'] - new_end).total_seconds()) < 2
    assert row['banks'] == [(auth_client._ids['quiz_bank_id'], 20), (bank_id, 15)]


def test_edit_refuses_an_end_before_the_start_an_empty_name_and_no_banks(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=2400)
    row = _session(code)
    for overrides, field in [
        ({'ends_at': utc8_local(row['starts_at'] - timedelta(minutes=1))}, 'ends_at'),
        ({'name': ' '}, 'name'),
        ({'banks': []}, 'banks'),
    ]:
        session_id, body = _edit_body(code, **overrides)
        response = auth_client.put(f'/api/class-sessions/{session_id}', json=body)
        assert response.status_code == 400, overrides
        assert response.get_json()['field'] == field


def test_the_course_of_a_class_session_cannot_change(auth_client):
    code = make_class_session(auth_client._ids)
    other = auth_client.post('/api/courses', json={'name': '別的課程'}).get_json()
    session_id, body = _edit_body(code, course_id=other['id'])
    response = auth_client.put(f'/api/class-sessions/{session_id}', json=body)
    assert response.status_code == 400
    assert response.get_json()['field'] == 'course'


def test_removing_a_bank_with_submissions_needs_the_confirm_flag_and_deletes_them(auth_client):
    ids = auth_client._ids
    code = make_class_session(ids)
    bank_id, question_id = _second_bank()
    _offer(code, bank_id)
    _hand_in(auth_client, code, bank_id, question_id)
    _hand_in(auth_client, code, ids['quiz_bank_id'], ids['question_id'])
    session_id, body = _edit_body(code, banks=[{'quiz_bank_id': ids['quiz_bank_id'], 'time_limit_minutes': None}])

    refused = auth_client.put(f'/api/class-sessions/{session_id}', json=body)
    assert refused.status_code == 409
    assert refused.get_json()['requires_confirm'] is True
    assert refused.get_json()['submission_count'] == 1
    assert len(_session(code)['banks']) == 2

    body['confirm'] = True
    response = auth_client.put(f'/api/class-sessions/{session_id}', json=body)
    assert response.status_code == 200, response.get_json()
    assert _session(code)['banks'] == [(ids['quiz_bank_id'], None)]
    with app_module.app.app_context():
        assert app_module.Submission.query.filter_by(quiz_bank_id=bank_id).count() == 0
    assert _count_submissions(code) == 1


def test_removing_a_bank_without_submissions_needs_no_confirm(auth_client):
    ids = auth_client._ids
    code = make_class_session(ids)
    bank_id, _ = _second_bank()
    _offer(code, bank_id)
    session_id, body = _edit_body(code, banks=[{'quiz_bank_id': bank_id, 'time_limit_minutes': None}])
    response = auth_client.put(f'/api/class-sessions/{session_id}', json=body)
    assert response.status_code == 200, response.get_json()
    assert _session(code)['banks'] == [(bank_id, None)]


def test_edit_data_names_the_banks_and_their_submission_counts(auth_client):
    ids = auth_client._ids
    code = make_class_session(ids, time_limit=20)
    _hand_in(auth_client, code, ids['quiz_bank_id'], ids['question_id'])
    session_id = _session(code)['id']
    body = auth_client.get(f'/api/class-sessions/{session_id}').get_json()
    assert body['started'] is True
    assert body['banks'] == [{'quiz_bank_id': ids['quiz_bank_id'], 'title': 'Timed Bank',
                              'time_limit_minutes': 20, 'n_subs': 1}]


# ---- actions ----

def _act(auth_client, code, action, **body):
    return auth_client.post(f'/api/class-sessions/{_session(code)["id"]}/{action}', json=body)


def test_end_now_ends_a_live_class_session(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=2400)
    response = _act(auth_client, code, 'end')
    assert response.status_code == 200, response.get_json()
    assert _session(code)['ends_at'] <= datetime.utcnow()
    assert auth_client.get(f'/quiz/{code}').status_code == 403  # the ended page


def test_start_now_keeps_the_length(auth_client):
    code = make_class_session(auth_client._ids, starts_in=3600, ends_in=3600 + 45 * 60)
    response = _act(auth_client, code, 'start-now')
    assert response.status_code == 200, response.get_json()
    row = _session(code)
    assert abs((row['starts_at'] - datetime.utcnow()).total_seconds()) < 5
    assert round((row['ends_at'] - row['starts_at']).total_seconds() / 60) == 45
    assert auth_client.get(f'/quiz/{code}').status_code == 200


def test_start_now_is_refused_for_a_live_class_session(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=2400)
    assert _act(auth_client, code, 'start-now').status_code == 400


def test_extend_moves_the_end_later(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=600)
    before = _session(code)['ends_at']
    response = _act(auth_client, code, 'extend', minutes=10)
    assert response.status_code == 200, response.get_json()
    assert _session(code)['ends_at'] - before == timedelta(minutes=10)


def test_reopen_opens_an_ended_class_session_for_30_minutes(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-7200, ends_in=-3600)
    response = _act(auth_client, code, 'reopen')
    assert response.status_code == 200, response.get_json()
    left = (_session(code)['ends_at'] - datetime.utcnow()).total_seconds()
    assert 29 * 60 < left <= 30 * 60
    assert auth_client.get(f'/quiz/{code}').status_code == 200


def test_reopen_is_refused_for_a_live_class_session(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=600)
    assert _act(auth_client, code, 'reopen').status_code == 400


# ---- delete ----

def test_delete_without_submissions_needs_no_confirm(auth_client):
    code = make_class_session(auth_client._ids)
    response = auth_client.delete(f'/api/class-sessions/{_session(code)["id"]}')
    assert response.status_code == 200
    assert _count_submissions(code) is None


def test_delete_with_submissions_needs_the_confirm_flag_and_deletes_them(auth_client):
    ids = auth_client._ids
    code = make_class_session(ids)
    _hand_in(auth_client, code, ids['quiz_bank_id'], ids['question_id'])
    session_id = _session(code)['id']

    refused = auth_client.delete(f'/api/class-sessions/{session_id}', json={})
    assert refused.status_code == 409
    assert refused.get_json()['submission_count'] == 1
    assert _count_submissions(code) == 1

    response = auth_client.delete(f'/api/class-sessions/{session_id}', json={'confirm': True})
    assert response.status_code == 200
    assert _count_submissions(code) is None
    with app_module.app.app_context():
        assert app_module.Submission.query.count() == 0


# ---- Quiz Bank delete cascade ----

def test_deleting_a_quiz_bank_deletes_class_sessions_left_with_no_bank(auth_client):
    ids = auth_client._ids
    alone = make_class_session(ids, name='只有這份')
    shared = make_class_session(ids, name='兩份')
    bank_id, _ = _second_bank()
    _offer(shared, bank_id)
    _hand_in(auth_client, alone, ids['quiz_bank_id'], ids['question_id'])

    response = auth_client.delete(f'/api/quiz-bank/{ids["quiz_bank_id"]}', json={'confirm': True})
    assert response.status_code == 200
    assert _count_submissions(alone) is None
    assert _session(shared)['banks'] == [(bank_id, None)]


# ---- ownership ----

def test_another_teachers_class_session_cannot_be_changed(auth_client):
    code = make_class_session(auth_client._ids, teacher_id=TEACHER_ROUTER_ID + 1)
    session_id, body = _edit_body(code)
    sign_in(auth_client, TEACHER_ROUTER_ID)
    assert auth_client.put(f'/api/class-sessions/{session_id}', json=body).status_code == 404
    assert auth_client.get(f'/api/class-sessions/{session_id}').status_code == 404
    for action in ('end', 'start-now', 'extend', 'reopen'):
        assert auth_client.post(f'/api/class-sessions/{session_id}/{action}', json={}).status_code == 404
    assert auth_client.delete(f'/api/class-sessions/{session_id}', json={'confirm': True}).status_code == 404


# ---- review fix 7 ----

def test_extend_is_refused_for_an_upcoming_class_session(auth_client):
    code = make_class_session(auth_client._ids, starts_in=3600, ends_in=7200)
    before = _session(code)['ends_at']
    response = _act(auth_client, code, 'extend', minutes=10)
    assert response.status_code == 400
    assert '進行中' in response.get_json()['error']
    assert _session(code)['ends_at'] == before


def test_an_ended_course_refuses_a_changed_end_in_the_edit(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=600, course_ended=True)
    before = _session(code)['ends_at']
    session_id, body = _edit_body(code, ends_at=utc8_local(before + timedelta(minutes=20)))
    response = auth_client.put(f'/api/class-sessions/{session_id}', json=body)
    assert response.status_code == 400
    assert response.get_json()['error'] == app_module.COURSE_ENDED_ERROR
    assert _session(code)['ends_at'] == before


def test_an_ended_course_still_lets_the_name_change_when_the_end_is_kept(auth_client):
    code = make_class_session(auth_client._ids, starts_in=-600, ends_in=600, course_ended=True)
    session_id, body = _edit_body(code, name='新的名稱')
    response = auth_client.put(f'/api/class-sessions/{session_id}', json=body)
    assert response.status_code == 200, response.get_json()
    assert _session(code)['name'] == '新的名稱'
