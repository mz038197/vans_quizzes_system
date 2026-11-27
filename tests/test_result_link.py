"""Result Links (ADR 0008)."""
from sqlalchemy import inspect

import app as app_module
from conftest import TEACHER_ROUTER_ID, sign_in


def _submit(client):
    ids = client._ids
    response = client.post(
        f"/api/quiz/{ids['access_code']}/submit",
        json={'student_name': 'Alice', 'answers': {str(ids['question_id']): 'A'}},
    )
    assert response.status_code == 200
    return response.get_json()


def test_submit_returns_an_unguessable_result_link(client):
    body = _submit(client)
    token = body['result_url'].rsplit('/', 1)[-1]
    assert len(token) >= 32
    assert str(body['submission_id']) != token
    page = client.get(body['result_url'])
    assert page.status_code == 200
    assert 'Alice' in page.get_data(as_text=True)


def test_numeric_submission_id_opens_nothing(client):
    body = _submit(client)
    assert client.get(f"/result/{body['submission_id']}").status_code == 404


def test_each_submission_has_its_own_token(client):
    first = _submit(client)['result_url']
    second = _submit(client)['result_url']
    assert first != second


def test_teacher_opens_a_submission_from_the_list(auth_client):
    body = _submit(auth_client)
    url = f"/quiz-bank/{auth_client._ids['quiz_bank_id']}/submissions/{body['submission_id']}"
    page = auth_client.get(url)
    assert page.status_code == 200
    assert 'Alice' in page.get_data(as_text=True)


def test_teacher_view_needs_sign_in_and_ownership(client):
    body = _submit(client)
    url = f"/quiz-bank/{client._ids['quiz_bank_id']}/submissions/{body['submission_id']}"
    assert client.get(url).status_code == 302
    sign_in(client, TEACHER_ROUTER_ID + 1)
    response = client.get(url)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/teacher-dashboard')


def test_teacher_view_refuses_a_submission_of_another_bank(auth_client):
    body = _submit(auth_client)
    with app_module.app.app_context():
        other = app_module.QuizBank(title='Other', access_code='OTH999', teacher_id=TEACHER_ROUTER_ID)
        app_module.db.session.add(other)
        app_module.db.session.commit()
        other_id = other.id
    assert auth_client.get(f"/quiz-bank/{other_id}/submissions/{body['submission_id']}").status_code == 404


def test_new_database_has_one_unique_rule_on_result_token(client):
    with app_module.app.app_context():
        insp = inspect(app_module.db.engine)
        token_indexes = [ix for ix in insp.get_indexes('submission') if ix['column_names'] == ['result_token']]
        token_constraints = [uc for uc in insp.get_unique_constraints('submission')
                             if uc['column_names'] == ['result_token']]
        assert len(token_indexes) + len(token_constraints) == 1


def test_new_database_indexes_teacher_id(client):
    """Every Teacher page filters Quiz Banks by teacher_id (ADR 0007)."""
    with app_module.app.app_context():
        insp = inspect(app_module.db.engine)
        assert ('teacher_id',) in {tuple(ix['column_names']) for ix in insp.get_indexes('quiz_bank')}
