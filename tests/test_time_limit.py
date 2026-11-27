"""API seams for Elapsed Time (the Time Limit belongs to the Class Session, issue #16)."""

from conftest import live_code


def test_submit_persists_elapsed_seconds_and_lists_it(auth_client):
    ids = auth_client._ids
    access_code = live_code(auth_client, time_limit=60)
    question_id = ids['question_id']
    quiz_bank_id = ids['quiz_bank_id']

    submit_response = auth_client.post(
        f'/api/quiz/{access_code}/submit',
        json={
            'student_name': 'Alice',
            'student_email': '',
            'answers': {str(question_id): 'A'},
            'elapsed_seconds': 2538,
        },
    )
    assert submit_response.status_code == 200
    body = submit_response.get_json()
    assert body['elapsed_seconds'] == 2538
    submission_id = body['submission_id']

    list_response = auth_client.get(f'/api/quiz-bank/{quiz_bank_id}/submissions')
    assert list_response.status_code == 200
    rows = list_response.get_json()
    match = next(row for row in rows if row['id'] == submission_id)
    assert match['elapsed_seconds'] == 2538


def test_submit_stores_elapsed_seconds_also_when_untimed(auth_client):
    # Spec #2: Elapsed Time is stored for every Submission (was: ignored when untimed).
    ids = auth_client._ids
    access_code = live_code(auth_client)
    question_id = ids['question_id']

    submit_response = auth_client.post(
        f'/api/quiz/{access_code}/submit',
        json={
            'student_name': 'Bob',
            'student_email': '',
            'answers': {str(question_id): 'A'},
            'elapsed_seconds': 120,
        },
    )
    assert submit_response.status_code == 200
    assert submit_response.get_json()['elapsed_seconds'] == 120
