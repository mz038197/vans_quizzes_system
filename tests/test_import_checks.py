import io

from conftest import app_module

GOOD_SINGLE = """type: single
title: while 停止
options:
  - 條件為 False 時
  - 永遠不停

while 迴圈什麼時候停止？

correct_answer: 條件為 False 時
"""

GOOD_FILL = """type: fill
title: 跳出
correct_answer: break

跳出迴圈的關鍵字是？
"""

MULTI_WITHOUT_ANSWER = """type: multiple
title: for 迴圈
options:
  - range
  - list

哪些可以用在 for 迴圈？
"""

BANK_HEAD = """title: 第二週
description: 迴圈
"""


def _md(*questions, head=None):
    parts = ([head] if head else []) + list(questions)
    return '\n---\n'.join(parts)


def _upload(client, url, text):
    return client.post(
        url,
        data={'file': (io.BytesIO(text.encode('utf-8')), 'quiz.md')},
        content_type='multipart/form-data',
    )


def _counts():
    with app_module.app.app_context():
        return app_module.QuizBank.query.count(), app_module.Question.query.count()


def test_create_preview_marks_the_question_with_a_problem(auth_client):
    text = _md(GOOD_SINGLE, GOOD_FILL, MULTI_WITHOUT_ANSWER, head=BANK_HEAD)

    response = _upload(auth_client, '/api/import-quiz-md/preview', text)

    assert response.status_code == 400
    data = response.get_json()
    assert data['success'] is False
    rows = data['questions']
    assert [row['index'] for row in rows] == [1, 2, 3]
    assert [row['title'] for row in rows] == ['while 停止', '跳出', 'for 迴圈']
    assert rows[0]['errors'] == [] and rows[1]['errors'] == []
    assert rows[2]['question_type'] == 'multiple_choice'
    assert any('沒有標記正確答案' in reason for reason in rows[2]['errors'])
    assert any('第 3 題' in error for error in data['errors'])


def test_create_preview_shows_the_answer_of_each_good_question(auth_client):
    text = _md(GOOD_SINGLE, GOOD_FILL, head=BANK_HEAD)

    response = _upload(auth_client, '/api/import-quiz-md/preview', text)

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert [row['answer'] for row in data['questions']] == ['條件為 False 時', 'break']
    assert all(row['errors'] == [] for row in data['questions'])


def test_create_confirm_refuses_a_file_with_a_problem(auth_client):
    before = _counts()
    text = _md(GOOD_SINGLE, MULTI_WITHOUT_ANSWER, head=BANK_HEAD)

    response = _upload(auth_client, '/api/import-quiz-md/confirm', text)

    assert response.status_code == 400
    assert response.get_json()['success'] is False
    assert _counts() == before


def test_create_confirm_imports_after_the_problem_is_fixed(auth_client):
    before_banks, before_questions = _counts()
    text = _md(GOOD_SINGLE, GOOD_FILL, head=BANK_HEAD)

    response = _upload(auth_client, '/api/import-quiz-md/confirm', text)

    assert response.status_code == 200
    assert _counts() == (before_banks + 1, before_questions + 2)


def test_append_preview_marks_the_question_with_a_problem(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    text = _md(GOOD_FILL, MULTI_WITHOUT_ANSWER)

    response = _upload(auth_client, f'/api/quiz-bank/{bank_id}/import-md/preview', text)

    assert response.status_code == 400
    rows = response.get_json()['questions']
    assert [row['errors'] == [] for row in rows] == [True, False]
    assert any('沒有標記正確答案' in reason for reason in rows[1]['errors'])


def test_append_confirm_refuses_a_file_with_a_problem(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    before = _counts()

    response = _upload(
        auth_client, f'/api/quiz-bank/{bank_id}/import-md/confirm', _md(GOOD_FILL, MULTI_WITHOUT_ANSWER),
    )

    assert response.status_code == 400
    assert _counts() == before


def test_practice_bank_question_without_category_is_marked_on_its_own_row(auth_client):
    head = """title: 練習
mode: practice
session_question_count: 1
category_ratios:
  基礎: 100
"""
    with_category = GOOD_FILL.replace('title: 跳出', 'title: 跳出\ncategory: 基礎')
    text = _md(MULTI_WITHOUT_ANSWER, with_category, GOOD_SINGLE, head=head)

    rows = _upload(auth_client, '/api/import-quiz-md/preview', text).get_json()['questions']

    assert rows[1]['errors'] == []
    assert any('category' in reason for reason in rows[2]['errors'])


def test_preview_pages_draw_problem_rows(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    manage = auth_client.get(f'/quiz-bank/{bank_id}?tab=import').get_data(as_text=True)
    create = auth_client.get('/create-quiz-bank?tab=import').get_data(as_text=True)

    for html in (manage, create):
        assert '/static/js/md_preview.js' in html
        assert '要先修正，才能匯入' in html
        assert 'MdPreview.render(' in html

    script = auth_client.get('/static/js/md_preview.js')
    assert script.status_code == 200
    assert 'is-error' in script.get_data(as_text=True)
    script.close()
