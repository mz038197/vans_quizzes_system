"""HTTP seam: one Class Session offers several Quiz Banks (ticket 10, issue #12).

Each Quiz Bank in a Class Session has its own Time Limit, its own Take and its own Submission.
A Class Session with more than one Quiz Bank opens a list page first.
"""

import json
import re
from datetime import datetime, timedelta

import app as app_module
from conftest import utc8_local


def _add_bank(title, quiz_mode='fixed', n_questions=1, teacher_id=None, folder_id=None):
    """Insert another Quiz Bank of the fixture Teacher with `n_questions` single-choice questions."""
    with app_module.app.app_context():
        bank = app_module.QuizBank.query.first()
        new = app_module.QuizBank(
            title=title, description='',
            teacher_id=teacher_id or bank.teacher_id, quiz_mode=quiz_mode, folder_id=folder_id,
        )
        app_module.db.session.add(new)
        app_module.db.session.flush()
        question_ids = []
        for n in range(n_questions):
            question = app_module.Question(
                title=f'{title} Q{n + 1}', question_text='What?', question_type='single_choice',
                question_data='{"options": ["A", "B"], "correct_answer": "A"}',
                points=1, order_index=n, quiz_bank_id=new.id,
            )
            app_module.db.session.add(question)
            app_module.db.session.flush()
            question_ids.append(question.id)
        app_module.db.session.commit()
        return new.id, question_ids


def _open(auth_client, banks, name='第 12 週 · 小考', starts_in=timedelta(0), length=timedelta(minutes=50)):
    now = datetime.utcnow()
    response = auth_client.post('/api/class-sessions', json={
        'new_course_name': '高一 3 班 · 115 上',
        'name': name,
        'starts_at': utc8_local(now + starts_in),
        'ends_at': utc8_local(now + starts_in + length),
        'banks': [{'quiz_bank_id': bank_id, 'time_limit_minutes': minutes} for bank_id, minutes in banks],
    })
    assert response.status_code == 201, response.get_json()
    return response.get_json()['code']


def _html(response):
    return response.get_data(as_text=True)


def test_each_quiz_bank_in_a_class_session_has_its_own_time_limit_and_submissions(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second, second_questions = _add_bank('迴圈與串列練習')
    code = _open(auth_client, [(first, 20), (second, None)])

    first_page = _html(auth_client.get(f'/quiz/{code}?bank={first}'))
    assert 'const timeLimitMinutes = 20;' in first_page
    second_page = _html(auth_client.get(f'/quiz/{code}?bank={second}'))
    assert 'const timeLimitMinutes = null;' in second_page
    assert '迴圈與串列練習' in second_page

    for bank_id, question_id in ((first, auth_client._ids['question_id']), (second, second_questions[0])):
        response = auth_client.post(f'/api/quiz/{code}/submit', json={
            'student_name': '學生甲', 'student_email': '', 'quiz_bank_id': bank_id,
            'answers': {str(question_id): 'A'}, 'elapsed_seconds': 60,
        })
        assert response.status_code == 200, response.get_json()
        assert response.get_json()['percentage'] == 100

    with app_module.app.app_context():
        class_session = app_module.ClassSession.query.filter_by(code=code).one()
        rows = sorted((s.quiz_bank_id, s.class_session_id, s.student_name) for s in app_module.Submission.query.all())
        assert rows == sorted([(first, class_session.id, '學生甲'), (second, class_session.id, '學生甲')])
        assert [(o.quiz_bank_id, o.time_limit_minutes) for o in class_session.offers] == [(first, 20), (second, None)]


def test_a_quiz_bank_not_in_the_class_session_is_not_found(auth_client):
    first = auth_client._ids['quiz_bank_id']
    other, _ = _add_bank('不在課堂裡')
    code = _open(auth_client, [(first, 20)])
    assert auth_client.get(f'/quiz/{code}?bank={other}').status_code == 404


def test_a_class_session_with_several_quiz_banks_opens_the_list_page(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second, _ = _add_bank('迴圈與串列練習', n_questions=3)
    code = _open(auth_client, [(first, 20), (second, None)], name='第 3 週')

    response = auth_client.get(f'/quiz/{code}')
    assert response.status_code == 200
    html = _html(response)
    assert 'id="class-session-hub"' in html
    assert 'id="student-info-section"' not in html  # not the start page of one Quiz Bank
    assert '第 3 週' in html
    assert '高一 3 班 · 115 上' in html
    assert 'id="hub-name"' in html

    items = re.findall(r'<a [^>]*class="hub-item"[^>]*data-bank="(\d+)"[^>]*href="([^"]+)"', html)
    assert [int(bank_id) for bank_id, _ in items] == [first, second]
    assert [href for _, href in items] == [f'/quiz/{code}?bank={first}', f'/quiz/{code}?bank={second}']
    assert '1 題 · 時限 20 分鐘' in html
    assert '3 題 · 不限時' in html


def test_the_list_page_names_a_practice_quiz_bank_by_its_draw_count(auth_client):
    first = auth_client._ids['quiz_bank_id']
    practice, _ = _add_bank('隨機練習題庫', quiz_mode='practice', n_questions=2)
    with app_module.app.app_context():
        app_module.db.session.get(app_module.QuizBank, practice).session_question_count = 10
        app_module.db.session.commit()
    code = _open(auth_client, [(first, None), (practice, 15)])
    assert '隨機抽 10 題 · 時限 15 分鐘' in _html(auth_client.get(f'/quiz/{code}'))


def test_a_class_session_with_one_quiz_bank_opens_its_start_page(auth_client):
    code = _open(auth_client, [(auth_client._ids['quiz_bank_id'], 20)])
    html = _html(auth_client.get(f'/quiz/{code}'))
    assert 'id="student-info-section"' in html
    assert 'id="class-session-hub"' not in html


def test_the_list_page_is_closed_outside_the_window(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second, _ = _add_bank('第二份')
    code = _open(auth_client, [(first, None), (second, None)], starts_in=timedelta(hours=1))
    response = auth_client.get(f'/quiz/{code}')
    assert response.status_code == 403
    assert 'id="class-session-hub"' not in _html(response)


def test_the_start_page_of_a_class_session_reads_the_name_kept_for_its_code(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second, _ = _add_bank('第二份')
    code = _open(auth_client, [(first, None), (second, None)])
    html = _html(auth_client.get(f'/quiz/{code}?bank={second}'))
    assert f'data-hub-code="{code}"' in html
    assert 'js/student_hub.js' in html


# ---- open-session dialog data (templates/_class_session_dialog.html) ----

def _dialog_data(auth_client, bank_id):
    html = _html(auth_client.get(f'/quiz-bank/{bank_id}'))
    match = re.search(r'<script type="application/json" id="cs-dialog-data">(.*?)</script>', html, re.S)
    assert match, 'no dialog data'
    return json.loads(match.group(1))


def test_the_time_limit_starts_at_the_one_this_quiz_bank_had_in_its_last_class_session(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second, _ = _add_bank('第二份')
    never, _ = _add_bank('沒開過課堂')
    _open(auth_client, [(first, 20), (second, 15)], name='上週', starts_in=timedelta(minutes=-30))
    _open(auth_client, [(first, 30)], name='這週', starts_in=timedelta(minutes=10))
    _open(auth_client, [(second, None)], name='剛剛', starts_in=timedelta(0))

    banks = {b['id']: b for b in _dialog_data(auth_client, first)['banks']}
    assert banks[first]['last_time_limit'] == 30
    assert banks[second]['last_time_limit'] is None  # the last one had no Time Limit
    assert banks[never]['last_time_limit'] is None


def _folder(auth_client, name, color='blue'):
    response = auth_client.post('/api/folders', json={'name': name, 'color': color})
    assert response.status_code == 201, response.get_json()
    return response.get_json()['folder']['id']


def test_the_dialog_groups_quiz_banks_by_folder_with_the_current_folder_first(auth_client):
    first = auth_client._ids['quiz_bank_id']
    alpha = _folder(auth_client, 'A 資料夾', 'green')
    beta = _folder(auth_client, 'B 資料夾', 'pink')
    in_beta, _ = _add_bank('在 B 裡', folder_id=beta)
    in_alpha, _ = _add_bank('在 A 裡', folder_id=alpha)

    data = _dialog_data(auth_client, in_beta)
    assert data['current_folder_id'] == beta
    assert [(f['id'], f['name'], f['color']) for f in data['folders']] == [
        (beta, 'B 資料夾', 'pink'), (alpha, 'A 資料夾', 'green')]
    banks = {b['id']: b for b in data['banks']}
    assert banks[in_beta]['folder_id'] == beta
    assert banks[in_alpha]['folder_id'] == alpha
    assert banks[first]['folder_id'] is None  # 未分類

    unfiled = _dialog_data(auth_client, first)
    assert unfiled['current_folder_id'] is None
    assert [f['id'] for f in unfiled['folders']] == [alpha, beta]


def test_the_dialog_lists_only_the_teachers_own_quiz_banks_and_folders(auth_client):
    other_bank, _ = _add_bank('別人的題庫', teacher_id=auth_client._ids['teacher_id'] + 1)
    data = _dialog_data(auth_client, auth_client._ids['quiz_bank_id'])
    assert other_bank not in [b['id'] for b in data['banks']]


def test_the_list_page_uses_the_student_layout_and_no_browser_dialog_box(auth_client):
    second, _ = _add_bank('第二份')
    code = _open(auth_client, [(auth_client._ids['quiz_bank_id'], None), (second, None)])
    html = _html(auth_client.get(f'/quiz/{code}'))
    assert '/static/css/tokens.css' in html and '/static/js/ui.js' in html
    assert '儀表板' not in html
    dialog_box = re.compile(r'\b(alert|confirm|prompt)\(')
    assert not dialog_box.findall(html)
    assert not dialog_box.findall(_html(auth_client.get('/static/js/student_hub.js')))
    assert 'style=' not in html.split('<main', 1)[1]


def test_hand_in_must_name_a_quiz_bank_the_class_session_offers(auth_client):
    """No fallback to the first offered Quiz Bank (review fix 6)."""
    first = auth_client._ids['quiz_bank_id']
    second, _ = _add_bank('迴圈與串列練習')
    other, _ = _add_bank('沒有提供的題庫')
    code = _open(auth_client, [(first, None), (second, None)])
    answers = {str(auth_client._ids['question_id']): 'A'}

    for bank_id in (None, '', 'abc', other):
        body = {'student_name': '學生甲', 'answers': answers}
        if bank_id is not None:
            body['quiz_bank_id'] = bank_id
        response = auth_client.post(f'/api/quiz/{code}/submit', json=body)
        assert response.status_code in (400, 404), (bank_id, response.status_code)

    with app_module.app.app_context():
        assert app_module.Submission.query.count() == 0
