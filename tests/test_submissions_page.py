"""HTTP seam: the Quiz Bank 成績 page in style A (ticket 05, #7).

Restyle only: the page, its stylesheet and its script are read through the Flask test client,
and the Submission APIs the page calls keep working.
"""

import re

from conftest import live_code
from test_design_system import HEX


def _page(auth_client):
    qb = auth_client._ids['quiz_bank_id']
    response = auth_client.get(f'/quiz-bank/{qb}/submissions')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _submit(client, name='學生甲', email='', answer='A'):
    ids = client._ids
    response = client.post(
        f'/api/quiz/{live_code(client)}/submit',
        json={'student_name': name, 'student_email': email, 'quiz_bank_id': ids['quiz_bank_id'], 'answers': {str(ids['question_id']): answer}},
    )
    assert response.status_code == 200
    return response.get_json()


def test_page_has_breadcrumb_back_to_quiz_banks_and_the_quiz_bank(auth_client):
    html = _page(auth_client)
    crumbs = re.search(r'<nav class="crumbs".*?</nav>', html, re.S).group(0)
    assert '題庫' in crumbs
    assert f'href="/quiz-bank/{auth_client._ids["quiz_bank_id"]}"' in crumbs
    assert 'Timed Bank' in crumbs
    assert re.search(r'aria-current="page">成績<', crumbs)


def test_page_head_has_title_and_csv_export(auth_client):
    html = _page(auth_client)
    head = re.search(r'<div class="page-head">.*?</div>\s*</div>', html, re.S).group(0)
    assert '<h1>' in head and '成績' in head
    assert 'Timed Bank' in head
    assert re.search(r'<button[^>]*id="export-csv"', head)
    assert '匯出 CSV' in head


def test_page_shows_four_number_cells(auth_client):
    html = _page(auth_client)
    kpis = re.search(r'<div class="kpis"[^>]*>(.*?)</div>\s*<!-- /kpis -->', html, re.S).group(1)
    assert len(re.findall(r'class="kpi"', kpis)) == 4
    for label in ['作答', '平均', '最高', '及格率']:
        assert label in kpis, label


def test_table_has_the_agreed_columns(auth_client):
    html = _page(auth_client)
    thead = re.search(r'<thead>(.*?)</thead>', html, re.S).group(1)
    headers = [re.sub(r'<[^>]+>', '', h).strip() for h in re.findall(r'<th[^>]*>(.*?)</th>', thead, re.S)]
    assert headers[:7] == ['名次', '姓名', 'Email', '課堂', '分數', '用時', '交卷時間']
    assert len(headers) == 8  # last column: 看答卷 and 刪除


def test_page_has_no_inline_styles_and_links_its_own_stylesheet(auth_client):
    html = _page(auth_client)
    content = html.split('<main', 1)[1]
    assert 'style="' not in content
    assert '/static/css/pages/submissions.css' in html


def test_page_stylesheet_takes_colours_from_the_tokens(client):
    response = client.get('/static/css/pages/submissions.css')
    assert response.status_code == 200
    css = response.get_data(as_text=True)
    assert not HEX.findall(css)
    assert not re.findall(r'rgba?\(', css)
    assert not re.findall(r'\b(white|black)\b(?!-)', css)


def test_delete_asks_with_the_in_page_danger_dialog(auth_client):
    html = _page(auth_client)
    assert '/static/js/submission_delete.js' in html  # one row or several: the shared dialog
    script = auth_client.get('/static/js/submission_delete.js').get_data(as_text=True)
    assert re.search(r'UI\.ask\([^;]*danger:\s*true', script, re.S)
    assert "'/api/submissions/delete'" in script and "method: 'POST'" in script


def test_rows_link_to_the_teacher_view_of_the_submission(auth_client):
    html = _page(auth_client)
    assert f'const SUBMISSIONS_URL = "/quiz-bank/{auth_client._ids["quiz_bank_id"]}/submissions";' in html
    assert 'href="${SUBMISSIONS_URL}/${s.id}"' in html
    assert '看答卷' in html


def test_list_view_and_delete_still_work(auth_client):
    qb = auth_client._ids['quiz_bank_id']
    body = _submit(auth_client, name='學生乙', email='b@example.com')

    rows = auth_client.get(f'/api/quiz-bank/{qb}/submissions').get_json()
    assert [r['student_name'] for r in rows] == ['學生乙']
    assert rows[0]['student_email'] == 'b@example.com'
    assert rows[0]['percentage'] == 100

    assert auth_client.get(f'/quiz-bank/{qb}/submissions/{body["submission_id"]}').status_code == 200

    deleted = auth_client.post('/api/submissions/delete', json={'ids': [body['submission_id']]})
    assert deleted.status_code == 200
    assert auth_client.get(f'/api/quiz-bank/{qb}/submissions').get_json() == []


# ---- Ticket 15 (#17): the Class Session filter, search and side panels ----

def test_filter_lists_class_sessions_with_status_and_keeps_the_chosen_one(auth_client):
    from conftest import make_class_session
    import app as app_module
    make_class_session(auth_client._ids, name='一班')
    code = make_class_session(auth_client._ids, name='二班', starts_in=3600, ends_in=7200)
    with app_module.app.app_context():
        cs_id = app_module.ClassSession.query.filter_by(code=code).one().id
    qb = auth_client._ids['quiz_bank_id']

    html = auth_client.get(f'/quiz-bank/{qb}/submissions?class_session={cs_id}').get_data(as_text=True)
    select = re.search(r'<select id="cs-filter".*?</select>', html, re.S).group(0)
    assert '全部課堂（2）' in select
    assert '一班 · 進行中' in select
    assert re.search(rf'<option value="{cs_id}"[^>]*selected[^>]*>二班 · 即將開始</option>', select)
    assert 'id="subs-search"' in html
    assert '分數分布' in html and '最常答錯' in html


def test_sessions_tab_grade_link_opens_the_page_filtered(auth_client):
    from conftest import make_class_session
    import app as app_module
    code = make_class_session(auth_client._ids, name='一班')
    with app_module.app.app_context():
        cs_id = app_module.ClassSession.query.filter_by(code=code).one().id
    qb = auth_client._ids['quiz_bank_id']
    html = auth_client.get(f'/quiz-bank/{qb}?tab=sessions').get_data(as_text=True)
    assert f'href="/quiz-bank/{qb}/submissions?class_session={cs_id}"' in html


def test_rows_mark_repeat_takes_and_time_up(auth_client):
    script = _page(auth_client).rsplit('<script', 1)[1]
    assert '第 ${s.take} 次' in script
    assert '時間到' in script


def test_grade_thresholds_come_from_grade_stats(auth_client):
    """Review fix 13: one PASS_PERCENT / HIGH_PERCENT, not 80/60 written in the page."""
    import grade_stats
    html = auth_client.get(f"/quiz-bank/{auth_client._ids['quiz_bank_id']}/submissions").get_data(as_text=True)
    assert f'const PASS_PERCENT = {grade_stats.PASS_PERCENT};' in html
    assert f'const HIGH_PERCENT = {grade_stats.HIGH_PERCENT};' in html
    assert 'pct >= 80' not in html and 'pct >= 60' not in html
