"""HTTP seam: the 課堂總表 and the 課程總表 (ticket 16, issue #18).

A grade sheet has one row per trimmed student name and one column per offered Quiz Bank.
Each cell is the latest score with its number of Takes, or 未作答.
"""

import csv
import io
import re
from datetime import datetime, timedelta

import app as app_module
from conftest import TEACHER_ROUTER_ID, sign_in, OWN_ORIGIN


def _bank(title, teacher_id=TEACHER_ROUTER_ID):
    with app_module.app.app_context():
        bank = app_module.QuizBank(title=title, description='', access_code=app_module.generate_access_code(),
                                   teacher_id=teacher_id, quiz_mode='fixed')
        app_module.db.session.add(bank)
        app_module.db.session.commit()
        return bank.id


def _course(name='高一 3 班 · 115 上', teacher_id=TEACHER_ROUTER_ID):
    with app_module.app.app_context():
        course = app_module.Course(teacher_id=teacher_id, name=name)
        app_module.db.session.add(course)
        app_module.db.session.commit()
        return course.id


def _session(course_id, name, banks, starts_in_days=0, teacher_id=TEACHER_ROUTER_ID):
    """A Class Session offering `banks` = [(quiz_bank_id, time_limit_minutes)] in that order."""
    now = datetime.utcnow() + timedelta(days=starts_in_days)
    with app_module.app.app_context():
        cs = app_module.ClassSession(teacher_id=teacher_id, course_id=course_id, name=name,
                                     code=app_module.new_class_session_code(),
                                     starts_at=now - timedelta(minutes=10), ends_at=now + timedelta(minutes=40))
        app_module.db.session.add(cs)
        app_module.db.session.flush()
        for position, (bank_id, minutes) in enumerate(banks):
            app_module.db.session.add(app_module.ClassSessionBank(
                class_session_id=cs.id, quiz_bank_id=bank_id, position=position, time_limit_minutes=minutes))
        app_module.db.session.commit()
        return cs.id


_clock = [datetime(2026, 11, 1, 2, 0)]


def _hand_in(class_session_id, bank_id, name, score, total=100):
    """Insert one Submission; each call hands in one minute after the previous one."""
    _clock[0] += timedelta(minutes=1)
    with app_module.app.app_context():
        sub = app_module.Submission(student_name=name, score=score, total_points=total, answers='{}',
                                    quiz_bank_id=bank_id, class_session_id=class_session_id,
                                    submitted_at=_clock[0])
        app_module.db.session.add(sub)
        app_module.db.session.commit()
        return sub.id


def _html(response):
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


def _rows(html):
    """The body rows of the sheet table as lists of cell texts (tags stripped, spaces squeezed)."""
    body = re.search(r'<tbody>(.*?)</tbody>', html, re.S).group(1)
    rows = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', body, re.S):
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)
        rows.append([' '.join(re.sub(r'<[^>]+>', ' ', c).split()) for c in cells])
    return rows


def _csv(response):
    assert response.status_code == 200
    assert response.mimetype == 'text/csv'
    return list(csv.reader(io.StringIO(response.get_data(as_text=True).lstrip('﻿'))))


def test_session_sheet_merges_names_after_trimming_spaces(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    cs = _session(_course(), '第 12 週 · 小考', [(bank, 20)])
    _hand_in(cs, bank, '王小明 ', 70)
    _hand_in(cs, bank, ' 王小明', 80)
    _hand_in(cs, bank, '陳怡君', 90)

    rows = _rows(_html(auth_client.get(f'/class-sessions/{cs}')))
    assert [r[0] for r in rows] == ['王小明', '陳怡君']


def test_session_sheet_cell_is_the_latest_score_with_the_take_count(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second = _bank('迴圈與串列練習')
    cs = _session(_course(), '第 12 週 · 小考', [(first, 20), (second, None)])
    _hand_in(cs, first, '李佳穎', 50)
    latest = _hand_in(cs, first, '李佳穎 ', 76)
    _hand_in(cs, first, '陳怡君', 98)
    _hand_in(cs, second, '陳怡君', 90)

    html = _html(auth_client.get(f'/class-sessions/{cs}'))
    assert _rows(html) == [['李佳穎', '76% ×2', '未作答'], ['陳怡君', '98%', '90%']]
    assert f'/quiz-bank/{first}/submissions/{latest}' in html  # the score opens that Submission


def test_session_sheet_columns_follow_the_class_session_order_with_their_numbers(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second = _bank('迴圈與串列練習')
    cs = _session(_course(), '第 12 週 · 小考', [(second, None), (first, 20)])
    _hand_in(cs, first, '陳怡君', 90)
    _hand_in(cs, first, '林冠宇', 71)

    html = _html(auth_client.get(f'/class-sessions/{cs}'))
    head = re.search(r'<thead>(.*?)</thead>', html, re.S).group(1)
    assert head.index('迴圈與串列練習') < head.index('Timed Bank')
    text = ' '.join(re.sub(r'<[^>]+>', ' ', head).split())
    assert '不限時 · 0 人交卷 · 平均 —' in text
    assert '20 分鐘 · 2 人交卷 · 平均 81%' in text
    assert _rows(html) == [['林冠宇', '未作答', '71%'], ['陳怡君', '未作答', '90%']]


def test_session_sheet_links_to_its_course_sheet(auth_client):
    course = _course('高一 3 班 · 115 上')
    cs = _session(course, '第 12 週 · 小考', [(auth_client._ids['quiz_bank_id'], None)])
    html = _html(auth_client.get(f'/class-sessions/{cs}'))
    crumbs = re.search(r'<nav class="crumbs".*?</nav>', html, re.S).group(0)
    assert f'href="/courses/{course}"' in crumbs and '高一 3 班 · 115 上' in crumbs
    head = re.search(r'<div class="page-head">.*?</p>', html, re.S).group(0)
    assert f'href="/courses/{course}"' in head
    assert '/static/css/tokens.css' in html and 'class="top"' in html


def test_session_sheet_csv_matches_the_screen(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second = _bank('迴圈與串列練習')
    cs = _session(_course(), '第 12 週 · 小考', [(first, 20), (second, None)])
    _hand_in(cs, first, '李佳穎', 50)
    _hand_in(cs, first, '李佳穎', 76.4, total=100)
    _hand_in(cs, second, '陳怡君', 9, total=10)

    rows = _csv(auth_client.get(f'/class-sessions/{cs}/sheet.csv'))
    assert rows == [['學生', 'Timed Bank', '迴圈與串列練習'],
                    ['李佳穎', '76 ×2', '未作答'],
                    ['陳怡君', '未作答', '90']]
    screen = _rows(_html(auth_client.get(f'/class-sessions/{cs}')))
    assert [[c.replace('%', '') for c in r] for r in screen] == rows[1:]


def test_teacher_sees_only_own_sheets(client):
    course = _course(teacher_id=TEACHER_ROUTER_ID + 1)
    cs = _session(course, '別人的課堂', [(_bank('別人的題庫', TEACHER_ROUTER_ID + 1), None)],
                  teacher_id=TEACHER_ROUTER_ID + 1)
    sign_in(client, TEACHER_ROUTER_ID)
    for path in (f'/class-sessions/{cs}', f'/class-sessions/{cs}/sheet.csv',
                 f'/courses/{course}', f'/courses/{course}/sheet.csv', '/class-sessions/9999', '/courses/9999'):
        assert client.get(path).status_code == 404, path
    sign_in(client, TEACHER_ROUTER_ID + 1)
    assert client.get(f'/class-sessions/{cs}').status_code == 200
    assert client.get(f'/courses/{course}').status_code == 200


def _course_with_three_sessions(auth_client):
    """Three Class Sessions (created out of start order) with 4 columns in all."""
    a = auth_client._ids['quiz_bank_id']
    b = _bank('迴圈與串列練習')
    course = _course('高一 3 班 · 115 上')
    week12 = _session(course, '第 12 週 · 小考', [(a, 20), (b, None)], starts_in_days=-1)
    week10 = _session(course, '第 10 週 · 小考', [(a, 20)], starts_in_days=-15)
    term = _session(course, '整學期練習', [(b, None)], starts_in_days=0)
    _session(_course('別的課程'), '別的課堂', [(a, None)])
    return course, a, b, week10, week12, term


def test_course_sheet_rows_cells_average_and_answered_count(auth_client):
    course, a, b, week10, week12, term = _course_with_three_sessions(auth_client)
    _hand_in(week10, a, '王小明', 70)
    _hand_in(week12, a, '王小明 ', 60)
    _hand_in(week12, a, '王小明', 81)
    _hand_in(term, b, ' 陳怡君', 95)

    html = _html(auth_client.get(f'/courses/{course}'))
    head = ' '.join(re.sub(r'<[^>]+>', ' ', re.search(r'<thead>(.*?)</thead>', html, re.S).group(1)).split())
    assert head.index('第 10 週') < head.index('第 12 週') < head.index('整學期練習')
    assert '別的課堂' not in html
    assert f'href="/class-sessions/{week12}"' in html  # a Class Session name opens its sheet
    assert _rows(html) == [
        ['王小明', '70%', '81% ×2', '未作答', '未作答', '76%', '2 / 4'],
        ['陳怡君', '未作答', '未作答', '未作答', '95%', '95%', '1 / 4'],
    ]


def test_course_sheet_csv_matches_the_screen(auth_client):
    course, a, b, week10, week12, term = _course_with_three_sessions(auth_client)
    _hand_in(week10, a, '王小明', 70)
    _hand_in(week12, b, '王小明', 85)
    _hand_in(week12, b, '王小明', 90)

    rows = _csv(auth_client.get(f'/courses/{course}/sheet.csv'))
    assert rows == [
        ['學生', '第 10 週 · 小考 · Timed Bank', '第 12 週 · 小考 · Timed Bank',
         '第 12 週 · 小考 · 迴圈與串列練習', '整學期練習 · 迴圈與串列練習', '平均', '寫了'],
        ['王小明', '70', '未作答', '90 ×2', '未作答', '80', '2 / 4'],
    ]
    screen = _rows(_html(auth_client.get(f'/courses/{course}')))
    assert [[c.replace('%', '') for c in r] for r in screen] == rows[1:]
