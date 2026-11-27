"""儀表板 numbers and the 題庫 page, driven through the HTTP routes (spec #2, issue #8)."""

import re
from datetime import datetime, timedelta

import app as app_module
from conftest import TEACHER_ROUTER_ID, ended_class_session_id, make_class_session, sign_in

def _bank(title, teacher_id=TEACHER_ROUTER_ID):
    with app_module.app.app_context():
        bank = app_module.QuizBank(
            title=title, description='',
            teacher_id=teacher_id, quiz_mode='fixed',
        )
        app_module.db.session.add(bank)
        app_module.db.session.commit()
        return bank.id


def _sub(bank_id, name, days_ago=0.0, score=1, total=1):
    class_session_id = ended_class_session_id(bank_id)
    with app_module.app.app_context():
        app_module.db.session.add(app_module.Submission(
            student_name=name, answers='{}', score=score, total_points=total,
            submitted_at=datetime.utcnow() - timedelta(days=days_ago), quiz_bank_id=bank_id,
            class_session_id=class_session_id,
        ))
        app_module.db.session.commit()


def _kpi(html, label):
    match = re.search(r'<div class="k">' + re.escape(label) + r'</div>\s*<div class="v">([^<]*)</div>'
                      r'(?:\s*<div class="d">([^<]*)</div>)?', html)
    assert match, f'KPI {label} not found'
    return match.group(1).strip(), (match.group(2) or '').strip()


def _without_dialog_data(html):
    """The page without the open-session dialog data, which lists every Quiz Bank of the Teacher."""
    return re.sub(r'<script type="application/json" id="cs-dialog-data">.*?</script>', '', html, flags=re.S)


def _dashboard(client):
    response = client.get('/teacher-dashboard')
    assert response.status_code == 200
    return _without_dialog_data(response.get_data(as_text=True))


def test_week_submissions_compare_with_last_week(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    for days in (0.1, 1, 6.5):
        _sub(bank, 'A', days_ago=days)
    _sub(bank, 'B', days_ago=8)
    _sub(bank, 'C', days_ago=20)  # older than two weeks: not in either week

    value, delta = _kpi(_dashboard(auth_client), '本週作答')
    assert value == '3'
    assert delta == '比上週 +2'


def test_week_submissions_delta_down_and_flat(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    _sub(bank, 'A', days_ago=9)
    _sub(bank, 'B', days_ago=10)
    assert _kpi(_dashboard(auth_client), '本週作答') == ('0', '比上週 -2')

    _sub(bank, 'C', days_ago=1)
    _sub(bank, 'D', days_ago=2)
    assert _kpi(_dashboard(auth_client), '本週作答') == ('2', '和上週持平')


def test_week_students_count_trimmed_distinct_names(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    other = _bank('Second Bank')
    _sub(bank, '王小明', days_ago=1)
    _sub(bank, ' 王小明 ', days_ago=2)
    _sub(other, '王小明\t', days_ago=3)
    _sub(other, '李小華', days_ago=0.5)
    _sub(other, '陳大文', days_ago=9)  # last week: not counted

    value, _ = _kpi(_dashboard(auth_client), '本週學生')
    assert value == '2'


def test_attention_counts_banks_with_average_below_60(auth_client):
    low = _bank('Low Bank')
    _sub(low, 'A', score=5, total=10)   # 50%
    _sub(low, 'B', score=6, total=10)   # 60% → average 55%
    edge = _bank('Edge Bank')
    _sub(edge, 'A', score=6, total=10)  # exactly 60%: fine
    _bank('Empty Bank')                 # no Submission: no average, fine

    html = _dashboard(auth_client)
    value, _ = _kpi(html, '需要注意')
    assert value == '1'
    assert 'href="/quiz-banks?filter=attention"' in html
    # the 需要注意 list names the Quiz Bank and the reason
    assert 'Low Bank' in html
    assert '平均 55%，低於 60%' in html


def test_dashboard_lists_recent_submissions(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    _sub(bank, 'Recent Student', days_ago=0.01)
    html = _dashboard(auth_client)
    assert 'Recent Student' in html


def test_dashboard_qr_panel_uses_local_library(auth_client):
    code = make_class_session(auth_client._ids)
    html = _dashboard(auth_client)
    assert '/static/js/vendor/qrcode.js' in html
    assert 'qrcode-generator' not in html  # not from a CDN
    assert '全螢幕投影' in html
    assert code in html  # the live Class Session is offered in 上課發題
    assert auth_client.get('/static/js/vendor/qrcode.js').status_code == 200


def test_quiz_banks_page_lists_banks_with_columns(auth_client):
    response = auth_client.get('/quiz-banks')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Timed Bank' in html
    assert '>代碼<' not in html  # Quiz Banks have no code (#16)
    for column in ('模式', '題數', '作答', '平均', '課堂'):
        assert f'>{column}<' in html
    assert '建立題庫' in html


def test_quiz_banks_attention_filter_lists_only_low_average(auth_client):
    low = _bank('Low Bank')
    _sub(low, 'A', score=1, total=10)
    good = _bank('Good Bank')
    _sub(good, 'A', score=9, total=10)

    html = auth_client.get('/quiz-banks').get_data(as_text=True)
    assert 'Low Bank' in html and 'Good Bank' in html and 'Timed Bank' in html
    assert '平均 10%，低於 60%' in html  # reason under the title of the row

    html = _without_dialog_data(auth_client.get('/quiz-banks?filter=attention').get_data(as_text=True))
    assert 'Low Bank' in html
    assert 'Good Bank' not in html
    assert 'Timed Bank' not in html


def test_teacher_sees_only_own_quiz_banks(client):
    other = _bank('Other Teacher Bank', teacher_id=TEACHER_ROUTER_ID + 1)
    _sub(other, 'Other Student', score=0, total=10, days_ago=1)

    sign_in(client, TEACHER_ROUTER_ID)
    for path in ('/teacher-dashboard', '/quiz-banks', '/quiz-banks?filter=attention'):
        html = _without_dialog_data(client.get(path).get_data(as_text=True))
        assert 'Other Teacher Bank' not in html, path
        assert 'Other Student' not in html, path
    html = _dashboard(client)
    assert _kpi(html, '本週作答')[0] == '0'
    assert _kpi(html, '需要注意')[0] == '0'
    assert _kpi(html, '進行中的課堂')[0] == '0'


def test_quiz_banks_page_needs_sign_in(client):
    response = client.get('/quiz-banks')
    assert response.status_code == 302


def test_nav_shows_dashboard_and_quiz_banks_only(auth_client):
    html = auth_client.get('/quiz-banks').get_data(as_text=True)
    nav = re.search(r'<nav class="top-nav".*?</nav>', html, re.S).group(0)
    assert '儀表板' in nav and '題庫' in nav
    assert 'href="/quiz-banks" aria-current="page"' in nav
    assert '新增題庫' not in nav
