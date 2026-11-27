import json

from conftest import app_module, sign_in

IMAGE = {
    'data_url': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
    'filename': 'dot.png',
}


def _questions(client, bank_id):
    response = client.get(f'/api/quiz-bank/{bank_id}/questions')
    assert response.status_code == 200
    return response.get_json()


def _add_question(client, bank_id, **fields):
    body = {
        'title': '迴圈',
        'question_text': '哪些可以用在 for 迴圈？',
        'question_type': 'multiple_choice',
        'points': 3,
        'category': '基礎',
        'question_data': {
            'options': ['range', 'list', 'int'],
            'correct_answers': ['range', 'list'],
            'explanation': 'int 不能迭代',
            'image': IMAGE,
        },
    }
    body.update(fields)
    response = client.post(f'/api/quiz-bank/{bank_id}/questions', json=body)
    assert response.status_code == 200
    return response.get_json()['question_id']


def _content(question):
    return {key: question.get(key) for key in (
        'title', 'question_text', 'question_type', 'points', 'category', 'question_data',
    )}


def test_copy_makes_a_new_question_with_the_same_content(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    source_id = _add_question(auth_client, bank_id)

    response = auth_client.post(f'/api/question/{source_id}/copy')

    assert response.status_code == 200
    copy_id = response.get_json()['question_id']
    assert copy_id != source_id
    by_id = {q['id']: q for q in _questions(auth_client, bank_id)}
    assert _content(by_id[copy_id]) == _content(by_id[source_id])
    assert by_id[copy_id]['question_data']['image']['filename'] == 'dot.png'
    assert by_id[copy_id]['question_data']['explanation'] == 'int 不能迭代'


def test_copy_is_placed_right_after_the_source(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    first_id = auth_client._ids['question_id']
    second_id = _add_question(auth_client, bank_id, title='第二題')

    copy_id = auth_client.post(f'/api/question/{first_id}/copy').get_json()['question_id']

    order = [q['id'] for q in _questions(auth_client, bank_id)]
    assert order == [first_id, copy_id, second_id]


def test_copy_is_an_independent_question(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    source_id = _add_question(auth_client, bank_id)
    copy_id = auth_client.post(f'/api/question/{source_id}/copy').get_json()['question_id']

    edit = auth_client.put(f'/api/question/{copy_id}', json={
        'title': '改過的題目',
        'question_data': {'options': ['A', 'B'], 'correct_answers': ['A']},
    })
    assert edit.status_code == 200
    assert auth_client.delete(f'/api/question/{copy_id}').status_code == 200

    by_id = {q['id']: q for q in _questions(auth_client, bank_id)}
    assert copy_id not in by_id
    assert by_id[source_id]['title'] == '迴圈'
    assert by_id[source_id]['question_data']['options'] == ['range', 'list', 'int']


def test_copy_needs_the_owner(client):
    question_id = client._ids['question_id']
    sign_in(client, 999)
    client.environ_base['HTTP_ORIGIN'] = 'http://localhost'

    response = client.post(f'/api/question/{question_id}/copy')

    assert response.status_code == 404
    with app_module.app.app_context():
        assert app_module.Question.query.count() == 1


def test_question_card_has_a_copy_button(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    question_id = auth_client._ids['question_id']

    html = auth_client.get(f'/quiz-bank/{bank_id}').get_data(as_text=True)

    assert f'copyQuestion({question_id})' in html
    assert '/copy' in html
