"""HTTP seam: the 課堂 tab on the Quiz Bank page and the open-session dialog data (ticket 09, #11)."""

import json
import re

import app as app_module
from conftest import TEACHER_ROUTER_ID, make_class_session


def _page(auth_client, query='?tab=sessions'):
    response = auth_client.get(f'/quiz-bank/{auth_client._ids["quiz_bank_id"]}{query}')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _sessions_panel(html):
    match = re.search(r'<section id="panel-sessions".*?(?=<section id="panel-|<div id="question-modal")', html, re.S)
    assert match, 'no 課堂 panel'
    return match.group(0)


def _dialog_data(html):
    match = re.search(r'<script type="application/json" id="cs-dialog-data">(.*?)</script>', html, re.S)
    assert match, 'no dialog data'
    return json.loads(match.group(1))


def test_tabs_are_questions_sessions_settings_import(auth_client):
    html = _page(auth_client)
    tabs = re.findall(r'<a [^>]*role="tab"[^>]*>(.*?)</a>', html, re.S)
    labels = [re.sub(r'<[^>]+>|\d', '', t).strip() for t in tabs]
    assert labels == ['題目', '課堂', '設定', '從 Markdown 追加']
    selected = re.search(r'<a [^>]*role="tab"[^>]*aria-selected="true"[^>]*>(.*?)</a>', html, re.S).group(1)
    assert '課堂' in selected


def test_sessions_tab_lists_live_then_upcoming_then_ended(auth_client):
    ids = auth_client._ids
    make_class_session(ids, starts_in=-7200, ends_in=-3600, name='上週小考', time_limit=30)
    make_class_session(ids, starts_in=3600, ends_in=7200, name='明天小考')
    make_class_session(ids, starts_in=-600, ends_in=2400, name='現在小考', time_limit=20)
    panel = _sessions_panel(_page(auth_client))
    names = re.findall(r'class="t-title">([^<]+)<', panel)
    assert names == ['現在小考', '明天小考', '上週小考']
    assert 'class="sp live"' in panel and 'class="sp soon"' in panel and 'class="sp done"' in panel
    assert '時限 20 分鐘' in panel
    assert '不限時' in panel
    assert '現在小考 的課程' in panel  # the Course name


def test_sessions_tab_shows_code_and_submission_count_in_that_class_session(auth_client):
    ids = auth_client._ids
    code = make_class_session(ids, name='現在小考')
    auth_client.post(f'/api/quiz/{code}/submit', json={
        'student_name': 'Student A', 'quiz_bank_id': ids['quiz_bank_id'],
        'answers': {str(ids['question_id']): 'A'}, 'elapsed_seconds': 10})
    panel = _sessions_panel(_page(auth_client))
    assert f'<span class="code">{code}</span>' in panel
    assert re.search(r'class="num"[^>]*>\s*1 人', panel)


def test_sessions_tab_without_class_sessions_says_so_and_offers_to_open_one(auth_client):
    panel = _sessions_panel(_page(auth_client))
    assert '沒有課堂' in panel
    assert f'data-open-session="{auth_client._ids["quiz_bank_id"]}"' in panel


def test_page_carries_the_open_session_dialog_with_the_last_used_open_course_first(auth_client):
    ids = auth_client._ids
    make_class_session(ids, name='舊的')  # Course 「舊的 的課程」
    make_class_session(ids, name='新的')  # opened later: last used
    make_class_session(ids, name='關了', course_ended=True)
    html = _page(auth_client, '')
    assert '/static/js/class_session_dialog.js' in html
    data = _dialog_data(html)
    assert [c['name'] for c in data['courses']] == ['新的 的課程', '舊的 的課程']
    assert data['default_course_id'] == data['courses'][0]['id']
    bank = next(b for b in data['banks'] if b['id'] == ids['quiz_bank_id'])
    assert bank['title'] == 'Timed Bank'
    # the header has a 開課堂 button with this Quiz Bank picked
    head = html.split('role="tablist"')[0]
    assert f'data-open-session="{ids["quiz_bank_id"]}"' in head


def test_sessions_tab_shows_only_class_sessions_of_this_teacher(auth_client):
    ids = auth_client._ids
    make_class_session(ids, name='別人的課堂', teacher_id=TEACHER_ROUTER_ID + 1)
    with app_module.app.app_context():
        assert app_module.ClassSession.query.count() == 1
    html = _page(auth_client)
    assert '別人的課堂' not in html
    assert [c['name'] for c in _dialog_data(html)['courses']] == []
