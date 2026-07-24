"""Seams for Take Order and Review Flag normalization / persistence."""

from practice_utils import normalize_review_flag_ids, build_take_order


class _FakeRng:
    """Deterministic permutation: reverse the list (for tests only)."""

    def shuffle(self, seq):
        seq.reverse()


def test_build_take_order_uses_rng_and_does_not_mutate_input():
    original = [1, 2, 3, 4]
    ordered = build_take_order(original, rng=_FakeRng())
    assert ordered == [4, 3, 2, 1]
    assert original == [1, 2, 3, 4]


def test_normalize_review_flag_ids_keeps_take_order_members_only():
    flagged = normalize_review_flag_ids(
        ['2', 3, '9', 2, 'x', None],
        take_order_ids=[1, 2, 3],
    )
    assert flagged == [2, 3]


def test_fixed_take_reuses_take_order_across_reloads(client):
    import app as app_module

    ids = client._ids
    access_code = ids['access_code']
    quiz_bank_id = ids['quiz_bank_id']

    with app_module.app.app_context():
        for i, text in enumerate(['Q2', 'Q3'], start=2):
            app_module.db.session.add(
                app_module.Question(
                    title=text,
                    question_text=text,
                    question_type='single_choice',
                    question_data='{"options": ["A", "B"], "correct_answer": "A"}',
                    points=1,
                    order_index=i,
                    quiz_bank_id=quiz_bank_id,
                )
            )
        app_module.db.session.commit()

    with app_module.app.app_context():
        bank_ids = {
            q.id
            for q in app_module.Question.query.filter_by(quiz_bank_id=quiz_bank_id).all()
        }

    first = client.get(f'/quiz/{access_code}')
    assert first.status_code == 200
    with client.session_transaction() as sess:
        first_order = list(sess[f'take_session_{access_code}']['question_ids'])
    assert len(first_order) == 3
    assert set(first_order) == bank_ids

    second = client.get(f'/quiz/{access_code}')
    assert second.status_code == 200
    with client.session_transaction() as sess:
        assert sess[f'take_session_{access_code}']['question_ids'] == first_order


def test_submit_persists_take_order_and_review_flags(client):
    import app as app_module
    import json

    ids = client._ids
    access_code = ids['access_code']
    q1 = ids['question_id']

    with app_module.app.app_context():
        q2 = app_module.Question(
            title='Q2',
            question_text='Q2?',
            question_type='single_choice',
            question_data='{"options": ["A", "B"], "correct_answer": "A"}',
            points=1,
            order_index=1,
            quiz_bank_id=ids['quiz_bank_id'],
        )
        app_module.db.session.add(q2)
        app_module.db.session.commit()
        q2_id = q2.id

    take_order = [q2_id, q1]
    with client.session_transaction() as sess:
        sess[f'take_session_{access_code}'] = {'question_ids': take_order}

    response = client.post(
        f'/api/quiz/{access_code}/submit',
        json={
            'student_name': 'Carol',
            'answers': {str(q1): 'A', str(q2_id): 'B'},
            'review_flag_question_ids': [q1, 999, str(q2_id)],
        },
    )
    assert response.status_code == 200
    submission_id = response.get_json()['submission_id']

    with app_module.app.app_context():
        submission = app_module.Submission.query.get(submission_id)
        assert json.loads(submission.session_question_ids) == take_order
        assert json.loads(submission.review_flag_question_ids) == [q1, q2_id]


def test_submit_without_take_session_uses_bank_order_not_new_permutation(client):
    """Hand-in must not invent a Take Order the student never saw."""
    import app as app_module
    import json

    ids = client._ids
    access_code = ids['access_code']
    q1 = ids['question_id']

    with app_module.app.app_context():
        q2 = app_module.Question(
            title='Q2',
            question_text='Q2?',
            question_type='single_choice',
            question_data='{"options": ["A", "B"], "correct_answer": "A"}',
            points=1,
            order_index=1,
            quiz_bank_id=ids['quiz_bank_id'],
        )
        app_module.db.session.add(q2)
        app_module.db.session.commit()
        q2_id = q2.id
        bank_order = [
            q.id
            for q in app_module.Question.query.filter_by(quiz_bank_id=ids['quiz_bank_id'])
            .order_by(app_module.Question.order_index)
            .all()
        ]

    response = client.post(
        f'/api/quiz/{access_code}/submit',
        json={
            'student_name': 'Dana',
            'answers': {str(q1): 'A', str(q2_id): 'A'},
        },
    )
    assert response.status_code == 200
    submission_id = response.get_json()['submission_id']

    with app_module.app.app_context():
        submission = app_module.Submission.query.get(submission_id)
        assert json.loads(submission.session_question_ids) == bank_order
