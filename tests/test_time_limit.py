"""API seams for Time Limit and Elapsed Time."""


def test_teacher_can_set_and_clear_time_limit(auth_client):
    quiz_bank_id = auth_client._ids['quiz_bank_id']

    set_response = auth_client.put(
        f'/api/quiz-bank/{quiz_bank_id}/practice-config',
        json={
            'quiz_mode': 'fixed',
            'session_question_count': 10,
            'scoring_mode': 'explicit',
            'scoring_total_points': 100,
            'time_limit_minutes': 60,
        },
    )
    assert set_response.status_code == 200
    set_body = set_response.get_json()
    assert set_body['time_limit_minutes'] == 60

    clear_response = auth_client.put(
        f'/api/quiz-bank/{quiz_bank_id}/practice-config',
        json={
            'quiz_mode': 'fixed',
            'session_question_count': 10,
            'scoring_mode': 'explicit',
            'scoring_total_points': 100,
            'time_limit_minutes': None,
        },
    )
    assert clear_response.status_code == 200
    assert clear_response.get_json()['time_limit_minutes'] is None


def test_submit_persists_elapsed_seconds_and_lists_it(auth_client):
    ids = auth_client._ids
    access_code = ids['access_code']
    question_id = ids['question_id']
    quiz_bank_id = ids['quiz_bank_id']

    config_response = auth_client.put(
        f'/api/quiz-bank/{quiz_bank_id}/practice-config',
        json={
            'quiz_mode': 'fixed',
            'session_question_count': 10,
            'scoring_mode': 'explicit',
            'scoring_total_points': 100,
            'time_limit_minutes': 60,
        },
    )
    assert config_response.status_code == 200

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


def test_submit_ignores_elapsed_seconds_when_bank_untimed(auth_client):
    ids = auth_client._ids
    access_code = ids['access_code']
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
    assert submit_response.get_json()['elapsed_seconds'] is None
