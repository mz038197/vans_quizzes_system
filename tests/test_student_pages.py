"""HTTP seam: the student pages in style A (start, take, result).

Ticket 03 (#5). Pages are read through the Flask test client as an anonymous student.
"""

import json
import re

import app as app_module


def _html(response):
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


def _add_question(quiz_bank_id, text, correct, points=1, order_index=1):
    with app_module.app.app_context():
        question = app_module.Question(
            title=text,
            question_text=text,
            question_type='single_choice',
            question_data=json.dumps({'options': ['A', 'B'], 'correct_answer': correct}),
            points=points,
            order_index=order_index,
            quiz_bank_id=quiz_bank_id,
        )
        app_module.db.session.add(question)
        app_module.db.session.commit()
        return question.id


def _set_bank(quiz_bank_id, **fields):
    with app_module.app.app_context():
        quiz_bank = app_module.db.session.get(app_module.QuizBank, quiz_bank_id)
        for name, value in fields.items():
            setattr(quiz_bank, name, value)
        app_module.db.session.commit()


def _fact(html, label):
    """The value in the start page fact cell with this label."""
    match = re.search(r'<b[^>]*>([^<]*)</b>\s*<span>' + re.escape(label) + '</span>', html)
    assert match, label
    return match.group(1).strip()


# ---- start page ----

def test_start_page_shows_question_count_time_limit_and_total_points(client):
    ids = client._ids
    _add_question(ids['quiz_bank_id'], 'Second?', 'B', points=4)
    _set_bank(ids['quiz_bank_id'], time_limit_minutes=20)

    html = _html(client.get(f'/quiz/{ids["access_code"]}'))

    assert 'Timed Bank' in html
    assert _fact(html, '題') == '2'
    assert _fact(html, '分鐘') == '20'
    assert _fact(html, '總分') == '5'


def test_start_page_without_time_limit_says_no_limit(client):
    html = _html(client.get(f'/quiz/{client._ids["access_code"]}'))
    assert _fact(html, '時限') == '不限'


def test_start_page_lists_the_three_rules_and_the_name_fields(client):
    html = _html(client.get(f'/quiz/{client._ids["access_code"]}'))
    assert '稍後再看' in html
    assert '成績連結' in html
    assert 'id="student-name"' in html
    assert 'id="student-email"' in html
    assert '選填' in html
    assert 'btn-lg' in html  # the large start button


def test_practice_start_page_uses_the_same_layout(client):
    ids = client._ids
    _add_question(ids['quiz_bank_id'], 'Second?', 'B')
    _set_bank(ids['quiz_bank_id'], quiz_mode='practice', session_question_count=1)

    html = _html(client.get(f'/quiz/{ids["access_code"]}'))

    assert _fact(html, '題') == '1'
    assert 'id="student-name"' in html
    assert 'btn-lg' in html


# ---- take page ----

def test_take_page_has_timer_question_pad_with_legend_and_phone_pad_button(client):
    ids = client._ids
    _add_question(ids['quiz_bank_id'], 'Second?', 'B')

    html = _html(client.get(f'/quiz/{ids["access_code"]}'))

    assert 'id="quiz-countdown"' in html
    assert 'id="question-pad"' in html
    legend = re.search(r'<ul class="qz-legend">(.*?)</ul>', html, re.S).group(1)
    for label in ['已作答', '稍後再看', '目前這題', '未作答']:
        assert label in legend, label
    assert 'id="qz-padbtn"' in html and 'aria-controls="qz-sheet"' in html
    # Every question in the Take Order is on the page, each with a Review Flag button.
    assert html.count('class="question-card') == 2
    assert html.count('class="btn review-flag-btn"') == 2


def test_take_page_css_gives_each_pad_state_a_style_and_a_phone_layout(client):
    css = _html(client.get('/static/css/pages/quiz.css'))
    for selector in ['.qz-pad .done', '.qz-pad .flag', '.qz-pad .now']:
        assert selector in css, selector
    phone = css[css.index('@media (max-width: 760px)'):]
    assert 'position: sticky' in phone  # timer and progress stay at the top
    assert '.qz-take.sheet-open .qz-sheet' in phone  # the pad slides up


def test_student_page_css_takes_every_colour_from_the_tokens(client):
    css = _html(client.get('/static/css/pages/quiz.css'))
    assert not re.findall(r'#[0-9a-fA-F]{3,8}\b', css)
    assert not re.findall(r'rgba?\(', css)
    assert not re.findall(r'\b(white|black)\b(?!-)', css)


# ---- result page (Result Link) ----

def _stat(html, label):
    match = re.search(r'<span>' + re.escape(label) + r'</span>\s*<b[^>]*>([^<]*)</b>', html)
    assert match, label
    return match.group(1).strip()


def _submit_two(client, **extra):
    """Q1 right, Q2 wrong and flagged; returns the Result Link path."""
    ids = client._ids
    second = _add_question(ids['quiz_bank_id'], 'Second?', 'B', points=3)
    client.get(f'/quiz/{ids["access_code"]}')  # fixes the Take Order
    payload = {
        'student_name': '學生甲',
        'answers': {str(ids['question_id']): 'A', str(second): 'A'},
        'review_flag_question_ids': [second],
    }
    payload.update(extra)
    response = client.post(f'/api/quiz/{ids["access_code"]}/submit', json=payload)
    assert response.status_code == 200
    return response.get_json()['result_url'], second


def test_result_page_shows_score_ring_and_stats(client):
    _set_bank(client._ids['quiz_bank_id'], time_limit_minutes=20)
    url, _ = _submit_two(client, elapsed_seconds=65)

    html = _html(client.get(url))

    assert 'class="qz-ring' in html
    assert '--p: 25' in html  # 1 of 4 points
    assert '1 / 4 分' in html
    assert _stat(html, '答對') == '1 / 2 題'
    assert _stat(html, '用時') == '1 分 5 秒'
    assert _stat(html, '稍後再看') == '1 題'
    assert '這個網址就是你的成績單' in html


def test_result_page_marks_each_question_right_or_wrong_with_both_answers(client):
    url, second = _submit_two(client)

    html = _html(client.get(url))

    items = dict(
        (int(qid), (state, flag))
        for state, qid, flag in re.findall(r'<article class="qz-rv (ok|bad)" id="rv-(\d+)"[^>]*data-flag="(\d)"', html)
    )
    assert items == {client._ids['question_id']: ('ok', '0'), second: ('bad', '1')}
    wrong = html[html.index(f'id="rv-{second}"'):]
    assert '你的答案' in wrong
    assert '正確答案' in wrong


def test_result_filter_counts_and_switches_on_the_page_only(client):
    url, _ = _submit_two(client)

    html = _html(client.get(url + '?f=bad'))

    buttons = dict(re.findall(r'<button type="button" data-filter="(\w+)"[^>]*>\s*([^<]*?)\s*</button>', html))
    assert buttons == {'all': '全部 2', 'bad': '答錯 1', 'flag': '稍後再看 1'}
    # The query string changes nothing: both questions are in the page; the filter only hides rows in the browser.
    assert len(re.findall(r'<article class="qz-rv ', html)) == 2
    assert 'hidden' not in re.search(r'<article class="qz-rv ok"[^>]*>', html).group(0)


ALL_TYPES = {
    'multiple_choice': {'options': ['x', 'y', 'z'], 'correct_answers': ['x', 'y']},
    'fill_blank': {'correct_answer': 'def'},
    'dropdown': {'options': ['p', 'q'], 'correct_answer': 'q'},
    'dropdown_fillblank': {
        'fillblank_text': 'a {{1}} b',
        'blanks': [{'options': ['m', 'n'], 'correct_answer': 'n'}],
    },
    'parsons': {
        'code_blocks': {'A': 'print(1)', 'B': 'print(2)'},
        'answer_slots': 2,
        'slot_answers': {'1': 'A', '2': 'B'},
    },
}


def test_every_question_type_shows_on_the_take_page_and_the_result_page(client):
    ids = client._ids
    with app_module.app.app_context():
        for index, (question_type, data) in enumerate(ALL_TYPES.items(), start=1):
            app_module.db.session.add(app_module.Question(
                title=question_type, question_text=f'{question_type} text', question_type=question_type,
                question_data=json.dumps(data), points=1, order_index=index, quiz_bank_id=ids['quiz_bank_id'],
            ))
        app_module.db.session.commit()

    take = _html(client.get(f'/quiz/{ids["access_code"]}'))
    for question_type in ['single_choice', *ALL_TYPES]:
        assert f'tb t-{question_type}' in take, question_type

    response = client.post(f'/api/quiz/{ids["access_code"]}/submit', json={
        'student_name': '學生甲', 'answers': {str(ids['question_id']): 'A'},
    })
    result = _html(client.get(response.get_json()['result_url']))
    assert len(re.findall(r'<article class="qz-rv ', result)) == 6
    assert _stat(result, '答對') == '1 / 6 題'
    assert result.count('正確答案') >= 5
