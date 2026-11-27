"""HTTP seam: the Quiz Bank 成績 page in style A (ticket 05, #7).

Restyle only: the page, its stylesheet and its script are read through the Flask test client,
and the Submission APIs the page calls keep working.
"""

import re

from test_design_system import HEX


def _page(auth_client):
    qb = auth_client._ids['quiz_bank_id']
    response = auth_client.get(f'/quiz-bank/{qb}/submissions')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _submit(client, name='學生甲', email='', answer='A'):
    ids = client._ids
    response = client.post(
        f'/api/quiz/{ids["access_code"]}/submit',
        json={'student_name': name, 'student_email': email, 'answers': {str(ids['question_id']): answer}},
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
    assert headers[:6] == ['名次', '姓名', 'Email', '分數', '用時', '交卷時間']
    assert len(headers) == 7  # last column: 看答卷 and 刪除


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
    script = html.rsplit('<script', 1)[1]
    assert re.search(r'UI\.ask\([^;]*danger:\s*true', script, re.S)
    assert "method: 'DELETE'" in script


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

    deleted = auth_client.delete(f'/api/submission/{body["submission_id"]}')
    assert deleted.status_code == 200
    assert auth_client.get(f'/api/quiz-bank/{qb}/submissions').get_json() == []
