"""Issue #16: a Quiz Bank has no code, no on/off switch and no Time Limit; every Submission belongs
to a Class Session."""
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from conftest import app_module, live_code


def test_quiz_bank_table_has_no_code_switch_or_time_limit(client):
    with app_module.app.app_context():
        columns = {c['name'] for c in inspect(app_module.db.engine).get_columns('quiz_bank')}
    assert not columns & {'access_code', 'is_active', 'time_limit_minutes'}


def test_a_code_that_is_no_class_session_is_not_found(client):
    live_code(client)
    for path in ('/quiz/ABC123', '/quiz/ABC123/play'):
        assert client.get(path).status_code == 404
    assert client.post('/api/quiz/ABC123/submit', json={'student_name': '甲'}).status_code == 404
    assert client.post('/api/quiz/ABC123/draw', json={}).status_code == 404


def test_the_on_off_switch_is_gone(auth_client):
    response = auth_client.post(f"/api/quiz-bank/{auth_client._ids['quiz_bank_id']}/toggle")
    assert response.status_code == 404


def test_settings_save_takes_no_time_limit(auth_client):
    response = auth_client.put(f"/api/quiz-bank/{auth_client._ids['quiz_bank_id']}/practice-config", json={
        'quiz_mode': 'fixed', 'scoring_mode': 'explicit', 'time_limit_minutes': 30,
    })
    assert response.status_code == 200
    assert 'time_limit_minutes' not in response.get_json()


def test_create_quiz_bank_returns_no_code(auth_client):
    body = auth_client.post('/create-quiz-bank', json={'title': '新的', 'description': ''}).get_json()
    assert body['quiz_bank_id'] and 'access_code' not in body


def test_teacher_pages_show_no_quiz_bank_code_or_switch(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    banks = auth_client.get('/quiz-banks').get_data(as_text=True)
    assert '<th>代碼</th>' not in banks and 'data-active' not in banks and 'data-code' not in banks
    manage = auth_client.get(f'/quiz-bank/{bank_id}?tab=settings').get_data(as_text=True)
    assert '題庫代碼' not in manage and 'time-limit-minutes' not in manage
    grades = auth_client.get(f'/quiz-bank/{bank_id}/submissions').get_data(as_text=True)
    assert '題庫代碼' not in grades and 'id="copy-link"' not in grades


def test_a_submission_without_a_class_session_is_refused_by_the_database(client):
    with app_module.app.app_context():
        app_module.db.session.add(app_module.Submission(
            student_name='甲', answers='{}', quiz_bank_id=client._ids['quiz_bank_id']))
        with pytest.raises(IntegrityError):
            app_module.db.session.commit()
        app_module.db.session.rollback()


def test_a_hand_in_records_its_class_session(client):
    code = live_code(client)
    ids = client._ids
    client.get(f'/quiz/{code}')
    response = client.post(f'/api/quiz/{code}/submit', json={
        'student_name': '甲', 'answers': {str(ids['question_id']): 'A'}, 'quiz_bank_id': ids['quiz_bank_id'],
    })
    assert response.status_code == 200
    with app_module.app.app_context():
        submission = app_module.db.session.get(app_module.Submission, response.get_json()['submission_id'])
        assert submission.class_session.code == code
