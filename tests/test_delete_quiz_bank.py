"""API seam: DELETE /api/quiz-bank/<id> — hard-delete with Submission confirm gate."""

from app import QuizBank, Question, Submission


def _submit(auth_client, student_name='Alice'):
    ids = auth_client._ids
    response = auth_client.post(
        f'/api/quiz/{ids["access_code"]}/submit',
        json={
            'student_name': student_name,
            'student_email': '',
            'answers': {str(ids['question_id']): 'A'},
        },
    )
    assert response.status_code == 200
    return response.get_json()['submission_id']


def test_delete_quiz_bank_without_submissions_succeeds(auth_client):
    quiz_bank_id = auth_client._ids['quiz_bank_id']
    question_id = auth_client._ids['question_id']

    response = auth_client.delete(f'/api/quiz-bank/{quiz_bank_id}')
    assert response.status_code == 200
    assert response.get_json()['message']

    with auth_client.application.app_context():
        assert QuizBank.query.get(quiz_bank_id) is None
        assert Question.query.get(question_id) is None


def test_delete_quiz_bank_with_submissions_requires_confirm(auth_client):
    quiz_bank_id = auth_client._ids['quiz_bank_id']
    _submit(auth_client, 'Alice')
    _submit(auth_client, 'Bob')

    response = auth_client.delete(f'/api/quiz-bank/{quiz_bank_id}')
    assert response.status_code == 409
    body = response.get_json()
    assert body['requires_confirm'] is True
    assert body['submission_count'] == 2

    with auth_client.application.app_context():
        assert QuizBank.query.get(quiz_bank_id) is not None
        assert Submission.query.filter_by(quiz_bank_id=quiz_bank_id).count() == 2


def test_delete_quiz_bank_with_confirm_removes_submissions(auth_client):
    ids = auth_client._ids
    quiz_bank_id = ids['quiz_bank_id']
    question_id = ids['question_id']
    submission_id = _submit(auth_client)

    response = auth_client.delete(
        f'/api/quiz-bank/{quiz_bank_id}',
        json={'confirm': True},
    )
    assert response.status_code == 200

    with auth_client.application.app_context():
        assert QuizBank.query.get(quiz_bank_id) is None
        assert Question.query.get(question_id) is None
        assert Submission.query.get(submission_id) is None
