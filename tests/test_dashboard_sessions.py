"""儀表板 and 題庫 page with Class Sessions (spec #2, issue #15), driven through the HTTP routes."""

import re
from datetime import datetime, timedelta

import app as app_module
from conftest import TEACHER_ROUTER_ID, make_class_session, sign_in

def _bank(title, teacher_id=TEACHER_ROUTER_ID, folder_id=None):
    with app_module.app.app_context():
        bank = app_module.QuizBank(
            title=title, description='',
            teacher_id=teacher_id, quiz_mode='fixed', folder_id=folder_id,
        )
        app_module.db.session.add(bank)
        app_module.db.session.commit()
        return bank.id


def _folder(name, color='green'):
    with app_module.app.app_context():
        folder = app_module.Folder(teacher_id=TEACHER_ROUTER_ID, name=name, color=color)
        app_module.db.session.add(folder)
        app_module.db.session.commit()
        return folder.id


def _session(bank_id, name, **kw):
    """A Class Session offering one Quiz Bank; times in seconds from now. Returns its code."""
    return make_class_session({'quiz_bank_id': bank_id}, name=name, **kw)


def _hand_in(code, bank_id, student='學生甲', score=1):
    with app_module.app.app_context():
        class_session = app_module.ClassSession.query.filter_by(code=code).one()
        app_module.db.session.add(app_module.Submission(
            student_name=student, answers='{}', score=score, total_points=1,
            quiz_bank_id=bank_id, class_session_id=class_session.id,
        ))
        app_module.db.session.commit()


def _end_course(code):
    with app_module.app.app_context():
        class_session = app_module.ClassSession.query.filter_by(code=code).one()
        class_session.course.ended_at = datetime.utcnow() - timedelta(minutes=5)
        app_module.db.session.commit()


def _kpi(html, label):
    match = re.search(r'<div class="k">' + re.escape(label) + r'</div>\s*<div class="v">([^<]*)</div>'
                      r'(?:\s*<div class="d">([^<]*)</div>)?', html)
    assert match, f'KPI {label} not found'
    return match.group(1).strip(), (match.group(2) or '').strip()


def _page(client, path):
    """The page without the open-session dialog data, which lists every Quiz Bank of the Teacher."""
    response = client.get(path)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    return re.sub(r'<script type="application/json" id="cs-dialog-data">.*?</script>', '<!-- cs-dialog-data -->',
                  html, flags=re.S)


def _row(html, bank_id):
    match = re.search(r'<tr[^>]*data-bank="%d".*?</tr>' % bank_id, html, re.S)
    assert match, f'row of Quiz Bank {bank_id} not found'
    return match.group(0)


def _cards(html):
    match = re.search(r'<section[^>]*id="live-sessions".*?</section>', html, re.S)
    assert match, 'Class Session cards not found'
    return match.group(0)


# ---- the first number: live and upcoming Class Sessions ----

def test_live_and_upcoming_class_session_counts(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    _session(bank, '三年一班 第一節')                               # live
    _session(bank, '三年二班 第一節', starts_in=-600)               # live
    _session(bank, '三年三班 明天', starts_in=3600, ends_in=6600)   # upcoming
    _session(bank, '已經下課', starts_in=-7200, ends_in=-120)        # ended
    _session(bank, '課程結束了', course_ended=True)                  # Course ended by hand: neither
    _session(bank, '課程到期了', course_ends_in=-60)                 # Course end date passed: neither
    _session(bank, '還沒開始的已結束課程', starts_in=3600, ends_in=6600, course_ended=True)
    other = _bank('Other Bank', teacher_id=TEACHER_ROUTER_ID + 1)
    _session(other, '別人的課堂', teacher_id=TEACHER_ROUTER_ID + 1)

    value, delta = _kpi(_page(auth_client, '/teacher-dashboard'), '進行中的課堂')
    assert value == '2'
    assert delta == '另有 1 堂即將開始'


def test_no_class_session_counts_zero(auth_client):
    assert _kpi(_page(auth_client, '/teacher-dashboard'), '進行中的課堂') == ('0', '另有 0 堂即將開始')


# ---- the cards and the 上課發題 list ----

def test_cards_show_live_and_upcoming_class_sessions_with_their_course(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    live = _session(bank, '三年一班 第一節', time_limit=20)
    soon = _session(bank, '三年三班 明天', starts_in=3600, ends_in=6600)
    done = _session(bank, '已經下課', starts_in=-7200, ends_in=-120)
    ended = _session(bank, '課程結束了')
    _end_course(ended)
    _hand_in(live, bank, '學生甲')
    _hand_in(live, bank, ' 學生甲 ')
    _hand_in(live, bank, '學生乙')

    html = _page(auth_client, '/teacher-dashboard')
    cards = _cards(html)
    assert '三年一班 第一節 的課程' in cards  # the Course name is on the card
    assert '三年一班 第一節' in cards and '三年三班 明天' in cards
    assert '已經下課' not in cards and '課程結束了' not in cards
    assert 'Timed Bank' in cards and '時限 20 分鐘' in cards and '不限時' in cards
    assert '2 人交卷' in cards  # trimmed names: one student who answered twice counts once
    assert '0 人交卷' in cards
    assert f'data-qr="{live}"' in cards and f'data-qr="{soon}"' in cards
    assert '投影 QR' in cards and '總表' in cards
    assert '進行中' in cards and '剩' in cards  # live: time left
    assert '即將開始' in cards and '後' in cards
    assert cards.count('<progress') == 1  # only the live card has the time bar

    # 上課發題: Class Session codes, grouped 進行中 / 即將開始, Course name before the Class Session name
    select = re.search(r'<select id="qr-bank".*?</select>', html, re.S).group(0)
    assert '<optgroup label="進行中">' in select and '<optgroup label="即將開始">' in select
    assert select.index('進行中') < select.index(live) < select.index('即將開始') < select.index(soon)
    assert '三年一班 第一節 的課程 · 三年一班 第一節' in select
    assert done not in select and ended not in select


def test_no_live_or_upcoming_class_session_shows_empty_cards(auth_client):
    html = _page(auth_client, '/teacher-dashboard')
    assert '目前沒有進行中或即將開始的課堂' in html
    assert 'id="qr-bank"' not in html


def test_open_class_session_button_on_dashboard_and_quiz_banks_page(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    for path in ('/teacher-dashboard', '/quiz-banks'):
        html = _page(auth_client, path)
        assert re.search(r'<button[^>]*class="btn btn-primary"[^>]*data-open-session=""', html), path
        assert '<!-- cs-dialog-data -->' in html, path
        assert '/static/js/class_session_dialog.js' in html, path
    # the ⋯ menu opens the dialog with the Quiz Bank picked: the row button carries the id
    assert f'data-id="{bank}"' in _row(_page(auth_client, '/quiz-banks'), bank)


# ---- 需要注意: a live Class Session alone is not a reason ----

def test_long_live_class_session_without_hand_in_does_not_need_attention(auth_client):
    # A Class Session can run for hours; no Submission yet is normal while Students work.
    quiet = _bank('Quiet Live Bank')
    _session(quiet, '長課堂', starts_in=-90 * 60)

    html = _page(auth_client, '/teacher-dashboard')
    value, _ = _kpi(html, '需要注意')
    assert value == '0'
    assert '還沒有人交卷' not in html

    html = _page(auth_client, '/quiz-banks?filter=attention')
    assert 'Quiet Live Bank' not in html
    # the live Class Session still shows in the Quiz Bank's status
    assert '● 1 堂進行中' in _row(_page(auth_client, '/quiz-banks'), quiet)


def test_attention_list_names_the_folder(auth_client):
    folder = _folder('期中考')
    bank = _bank('Folder Bank', folder_id=folder)
    _hand_in(_session(bank, '低分', starts_in=-20 * 60), bank, score=0)
    html = _page(auth_client, '/teacher-dashboard')
    attn = re.search(r'<section[^>]*dash-attn.*?</section>', html, re.S).group(0)
    assert 'Folder Bank' in attn and '期中考' in attn


# ---- 題庫 table: the Class Session status of each Quiz Bank ----

def test_quiz_bank_class_session_status_text(auth_client):
    live = _bank('Live Bank')
    _session(live, '第一節')
    _session(live, '第二節', starts_in=-120)
    _session(live, '明天', starts_in=86400, ends_in=90000)

    starts = datetime.utcnow() + timedelta(hours=30)
    soon = _bank('Soon Bank')
    _session(soon, '後天', starts_in=40 * 3600, ends_in=41 * 3600)
    _session(soon, '明天', starts_in=30 * 3600, ends_in=31 * 3600)

    none = _bank('Done Bank')
    _session(none, '已經下課', starts_in=-7200, ends_in=-120)
    _session(none, '課程結束了', course_ended=True)

    html = _page(auth_client, '/quiz-banks')
    assert '>課堂<' in html  # the column
    assert '● 2 堂進行中' in _row(html, live)
    wall = starts + timedelta(hours=8)
    assert f'下一堂 {wall.month}/{wall.day} {wall:%H:%M}' in _row(html, soon)
    assert '沒有課堂' in _row(html, none)
    assert '沒有課堂' in _row(html, auth_client._ids['quiz_bank_id'])


def test_folder_card_shows_live_class_sessions(auth_client):
    busy = _folder('上課中')
    a = _bank('A', folder_id=busy)
    b = _bank('B', folder_id=busy)
    _session(a, '第一節')
    _session(b, '第二節')
    _session(b, '明天', starts_in=3600, ends_in=7200)
    quiet = _folder('沒在用', color='pink')
    _bank('C', folder_id=quiet)

    html = _page(auth_client, '/quiz-banks')
    card = re.search(r'<a class="fcard[^"]*" data-folder="%d".*?</a>' % busy, html, re.S).group(0)
    assert '● 2 堂進行中' in card
    card = re.search(r'<a class="fcard[^"]*" data-folder="%d".*?</a>' % quiet, html, re.S).group(0)
    assert '進行中' not in card


def test_other_teachers_class_sessions_do_not_show(client):
    other = _bank('Other Bank', teacher_id=TEACHER_ROUTER_ID + 1)
    _session(other, '別人的課堂', teacher_id=TEACHER_ROUTER_ID + 1, starts_in=-20 * 60)
    sign_in(client, TEACHER_ROUTER_ID)
    html = _page(client, '/teacher-dashboard')
    assert '別人的課堂' not in html
    assert _kpi(html, '進行中的課堂')[0] == '0'
    assert _kpi(html, '需要注意')[0] == '0'


def test_each_card_opens_the_edit_class_session_dialog(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    live = _session(bank, '三年一班 第一節')
    soon = _session(bank, '三年三班 明天', starts_in=3600, ends_in=6600)
    with app_module.app.app_context():
        ids = [app_module.ClassSession.query.filter_by(code=code).one().id for code in (live, soon)]

    html = _page(auth_client, '/teacher-dashboard')

    cards = _cards(html)
    for class_session_id, name in zip(ids, ('三年一班 第一節', '三年三班 明天')):
        assert f'data-cs-edit="{class_session_id}"' in cards
        assert f'aria-label="編輯「{name}」"' in cards
    assert '/static/js/class_session_actions.js' in html
