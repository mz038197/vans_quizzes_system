"""HTTP seam: the Quiz Bank manage page and the create page (ticket 04, #6).

Pages are read through the Flask test client, as a signed-in Teacher.
"""

import re

from conftest import app_module


def _page(auth_client, query=''):
    response = auth_client.get(f'/quiz-bank/{auth_client._ids["quiz_bank_id"]}{query}')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _selected_tab(html):
    tab = re.search(r'<a [^>]*role="tab"[^>]*aria-selected="true"[^>]*>(.*?)</a>', html, re.S)
    assert tab, 'no selected tab'
    return re.sub(r'<[^>]+>', '', tab.group(1)).strip()


def test_manage_page_has_question_settings_and_import_tabs(auth_client):
    html = _page(auth_client)
    tabs = re.findall(r'<a [^>]*role="tab"[^>]*>(.*?)</a>', html, re.S)
    labels = [re.sub(r'<[^>]+>|\d', '', t).strip() for t in tabs]
    assert labels == ['題目', '設定', '從 Markdown 追加']
    assert _selected_tab(html).startswith('題目')


def test_manage_page_opens_the_tab_named_in_the_link(auth_client):
    assert _selected_tab(_page(auth_client, '?tab=settings')) == '設定'
    assert _selected_tab(_page(auth_client, '?tab=import')) == '從 Markdown 追加'
    assert _selected_tab(_page(auth_client, '?tab=nonsense')).startswith('題目')


def _add_question(auth_client, **fields):
    body = {
        'title': 'Q', 'question_text': 'text', 'question_type': 'fill_blank',
        'question_data': {'correct_answer': 'break'}, 'points': 2,
    }
    body.update(fields)
    response = auth_client.post(f'/api/quiz-bank/{auth_client._ids["quiz_bank_id"]}/questions', json=body)
    assert response.status_code in (200, 201), response.get_json()


def _section(html, name):
    match = re.search(rf'<section id="panel-{name}".*?(?=<section id="panel-|<div id="question-modal")', html, re.S)
    assert match, name
    return match.group(0)


def test_question_card_shows_type_category_points_and_answer(auth_client):
    _add_question(auth_client, title='跳出迴圈', category='迴圈')
    cards = _section(_page(auth_client), 'questions')
    # fixture question: single choice, no category, 1 point, correct "A"
    assert 'class="tb t-single_choice"' in cards
    assert 'class="tb t-fill_blank"' in cards
    assert 'chip-none">未分類' in cards
    assert '<span class="chip">迴圈</span>' in cards
    assert '2.0 分' in cards
    assert '正確答案：break' in cards
    assert 'is-correct' in cards  # single-choice correct option marked
    assert cards.count('onclick="editQuestion(') == 2
    assert cards.count('onclick="deleteQuestion(') == 2


def test_question_card_marks_a_question_with_an_image(auth_client):
    image = {'data_url': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
             'mime_type': 'image/png', 'filename': 'a.png'}
    _add_question(auth_client, question_data={'correct_answer': 'x', 'image': image})
    assert '附圖' in _section(_page(auth_client), 'questions')


def test_side_summary_counts_types_and_categories_and_shows_settings(auth_client):
    _add_question(auth_client, category='迴圈')
    _add_question(auth_client, category='迴圈')
    html = _section(_page(auth_client), 'questions')
    types = re.search(r'id="type-summary".*?</div>\s*</div>\s*(?=<div class="panel side-box")', html, re.S).group(0)
    assert re.search(r'單選題</span>.*?<span class="c num">1</span>', types, re.S)
    assert re.search(r'填空題</span>.*?<span class="c num">2</span>', types, re.S)
    cats = re.search(r'id="category-summary".*?(?=id="settings-summary")', html, re.S).group(0)
    assert re.search(r'迴圈</span>.*?<span class="c num">2</span>', cats, re.S)
    assert re.search(r'未分類</span>.*?<span class="c num">1</span>', cats, re.S)
    summary = re.search(r'id="settings-summary".*?</dl>', html, re.S).group(0)
    assert '固定測驗' in summary
    assert '各題分數' in summary
    assert '5 分' in summary  # 1 + 2 + 2 points


def test_empty_quiz_bank_offers_add_and_markdown_import(auth_client):
    auth_client.delete(f'/api/question/{auth_client._ids["question_id"]}')
    cards = _section(_page(auth_client), 'questions')
    assert '還沒有題目' in cards
    assert 'showAddQuestionModal()' in cards
    assert 'data-tab-link="import"' in cards


def test_settings_tab_has_mode_cards_ratio_total_scoring_time_limit_and_hidden_save_bar(auth_client):
    html = _page(auth_client, '?tab=settings')
    settings = _section(html, 'settings')
    assert re.search(r'name="quiz_mode" value="fixed" checked', settings)
    assert 'name="quiz_mode" value="practice"' in settings
    assert 'id="ratio-total"' in settings
    assert re.search(r'name="scoring_mode" value="explicit" checked', settings)
    assert 'name="scoring_mode" value="average"' in settings
    assert 'id="time-limit-minutes"' in settings
    assert re.search(r'<div class="savebar" id="savebar" hidden', settings)
    assert '儲存設定' in settings


def test_settings_tab_shows_the_saved_settings(auth_client):
    response = auth_client.put(
        f'/api/quiz-bank/{auth_client._ids["quiz_bank_id"]}/practice-config',
        json={'quiz_mode': 'practice', 'session_question_count': 1, 'category_ratios': {'未分類': 100},
              'scoring_mode': 'average', 'scoring_total_points': 50, 'time_limit_minutes': 20},
    )
    assert response.status_code == 200, response.get_json()
    html = _page(auth_client, '?tab=settings')
    settings = _section(html, 'settings')
    assert re.search(r'name="quiz_mode" value="practice" checked', settings)
    assert re.search(r'name="scoring_mode" value="average" checked', settings)
    assert re.search(r'id="time-limit-minutes"[^>]*value="20"', settings)
    summary = re.search(r'id="settings-summary".*?</dl>', html, re.S).group(0)
    assert '隨機練習' in summary and '依題數平均' in summary and '50 分' in summary and '20 分鐘' in summary


def test_import_tab_has_drop_area_and_template_link(auth_client):
    imports = _section(_page(auth_client, '?tab=import'), 'import')
    assert 'class="drop"' in imports
    assert 'type="file" id="append-md-file"' in imports
    assert '/api/quiz-bank/import-md/questions-template' in imports
    assert 'id="append-preview" hidden' in imports


def test_manage_page_head_links_pdf_grades_and_add_question(auth_client):
    qb = auth_client._ids['quiz_bank_id']
    html = _page(auth_client)
    head = re.search(r'<div class="page-head">.*?</div>\s*</div>', html, re.S).group(0)
    assert f'/quiz-bank/{qb}/export-pdf' in head
    assert f'/quiz-bank/{qb}/submissions' in head
    assert 'showAddQuestionModal()' in head
    assert 'class="crumbs"' in html


def test_page_stylesheet_takes_every_colour_from_the_tokens(client):
    response = client.get('/static/css/pages/quiz_bank.css')
    assert response.status_code == 200
    css = response.get_data(as_text=True)
    assert not re.findall(r'#[0-9a-fA-F]{3,8}\b', css)
    assert not re.findall(r'rgba?\(', css)
    assert not re.findall(r'\b(white|black)\b(?!-)', css)


def _create_page(auth_client, query=''):
    response = auth_client.get(f'/create-quiz-bank{query}')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _picked(html):
    card = re.search(r'<a [^>]*data-pick="[^"]+"[^>]*aria-current="true"[^>]*>(.*?)</a>', html, re.S)
    assert card, 'no picked card'
    return card.group(1)


def test_create_page_offers_manual_and_markdown_choice_cards(auth_client):
    html = _create_page(auth_client)
    assert '手動建立' in _picked(html)
    assert 'id="create-quiz-form"' in html
    assert 'id="md-file"' not in html.split('id="import-tab"')[0]


def test_create_page_opens_the_markdown_card_from_the_link(auth_client):
    html = _create_page(auth_client, '?tab=import')
    assert '從 Markdown 匯入' in _picked(html)
    assert re.search(r'id="manual-tab"[^>]*hidden', html)
    assert 'class="drop"' in html
    assert '/api/import-quiz-md/template' in html


def test_manual_create_still_makes_a_quiz_bank(auth_client):
    response = auth_client.post('/create-quiz-bank', json={'title': '新的題庫', 'description': ''})
    assert response.status_code == 200
    bank_id = response.get_json()['quiz_bank_id']
    assert auth_client.get(f'/quiz-bank/{bank_id}').status_code == 200
