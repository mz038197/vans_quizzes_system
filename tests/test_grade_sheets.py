"""HTTP seam: the 課堂總表 and the 課程總表 (ticket 16, issue #18).

A grade sheet has one row per trimmed student name and one column per offered Quiz Bank.
Each cell is the latest score with its number of Takes, or 未作答.
"""

import csv
import io
import re

from conftest import (TEACHER_ROUTER_ID, sign_in, hand_in, make_bank, make_course, make_sheet_session,
                      page_html, sheet_rows)


def _csv(response):
    assert response.status_code == 200
    assert response.mimetype == 'text/csv'
    return list(csv.reader(io.StringIO(response.get_data(as_text=True).lstrip('﻿'))))


def test_session_sheet_merges_names_after_trimming_spaces(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    cs = make_sheet_session(make_course(), '第 12 週 · 小考', [(bank, 20)])
    hand_in(cs, bank, '王小明 ', 70)
    hand_in(cs, bank, ' 王小明', 80)
    hand_in(cs, bank, '陳怡君', 90)

    rows = sheet_rows(page_html(auth_client.get(f'/class-sessions/{cs}')))
    assert [r[0] for r in rows] == ['王小明', '陳怡君']


def test_session_sheet_cell_is_the_latest_score_with_the_take_count(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second = make_bank('迴圈與串列練習')
    cs = make_sheet_session(make_course(), '第 12 週 · 小考', [(first, 20), (second, None)])
    hand_in(cs, first, '李佳穎', 50)
    latest = hand_in(cs, first, '李佳穎 ', 76)
    hand_in(cs, first, '陳怡君', 98)
    hand_in(cs, second, '陳怡君', 90)

    html = page_html(auth_client.get(f'/class-sessions/{cs}'))
    assert sheet_rows(html) == [['李佳穎', '76% ×2', '未作答'], ['陳怡君', '98%', '90%']]
    assert f'/quiz-bank/{first}/submissions/{latest}' in html  # the score opens that Submission


def test_session_sheet_columns_follow_the_class_session_order_with_their_numbers(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second = make_bank('迴圈與串列練習')
    cs = make_sheet_session(make_course(), '第 12 週 · 小考', [(second, None), (first, 20)])
    hand_in(cs, first, '陳怡君', 90)
    hand_in(cs, first, '林冠宇', 71)

    html = page_html(auth_client.get(f'/class-sessions/{cs}'))
    head = re.search(r'<thead>(.*?)</thead>', html, re.S).group(1)
    assert head.index('迴圈與串列練習') < head.index('Timed Bank')
    text = ' '.join(re.sub(r'<[^>]+>', ' ', head).split())
    assert '不限時 · 0 人交卷 · 平均 —' in text
    assert '20 分鐘 · 2 人交卷 · 平均 81%' in text
    assert sheet_rows(html) == [['林冠宇', '未作答', '71%'], ['陳怡君', '未作答', '90%']]


def test_session_sheet_links_to_its_course_sheet(auth_client):
    course = make_course('高一 3 班 · 115 上')
    cs = make_sheet_session(course, '第 12 週 · 小考', [(auth_client._ids['quiz_bank_id'], None)])
    html = page_html(auth_client.get(f'/class-sessions/{cs}'))
    crumbs = re.search(r'<nav class="crumbs".*?</nav>', html, re.S).group(0)
    assert f'href="/courses/{course}"' in crumbs and '高一 3 班 · 115 上' in crumbs
    head = re.search(r'<div class="page-head">.*?</p>', html, re.S).group(0)
    assert f'href="/courses/{course}"' in head
    assert '/static/css/tokens.css' in html and 'class="top"' in html


def test_session_sheet_csv_has_a_number_and_a_take_count_per_column(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second = make_bank('迴圈與串列練習')
    cs = make_sheet_session(make_course(), '第 12 週 · 小考', [(first, 20), (second, None)])
    hand_in(cs, first, '李佳穎', 50)
    hand_in(cs, first, '李佳穎', 76.4, total=100)
    hand_in(cs, second, '陳怡君', 9, total=10)

    rows = _csv(auth_client.get(f'/class-sessions/{cs}/sheet.csv'))
    # Each column is two CSV columns: the latest score as a plain number (blank when not answered)
    # and the number of Takes, so a spreadsheet can calculate with the scores.
    assert rows == [['學生', 'Timed Bank', 'Timed Bank 次數', '迴圈與串列練習', '迴圈與串列練習 次數'],
                    ['李佳穎', '76', '2', '', '0'],
                    ['陳怡君', '', '0', '90', '1']]


def test_teacher_sees_only_own_sheets(client):
    course = make_course(teacher_id=TEACHER_ROUTER_ID + 1)
    cs = make_sheet_session(course, '別人的課堂', [(make_bank('別人的題庫', TEACHER_ROUTER_ID + 1), None)],
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
    b = make_bank('迴圈與串列練習')
    course = make_course('高一 3 班 · 115 上')
    week12 = make_sheet_session(course, '第 12 週 · 小考', [(a, 20), (b, None)], starts_in_days=-1)
    week10 = make_sheet_session(course, '第 10 週 · 小考', [(a, 20)], starts_in_days=-15)
    term = make_sheet_session(course, '整學期練習', [(b, None)], starts_in_days=0)
    make_sheet_session(make_course('別的課程'), '別的課堂', [(a, None)])
    return course, a, b, week10, week12, term


def test_course_sheet_rows_cells_average_and_answered_count(auth_client):
    course, a, b, week10, week12, term = _course_with_three_sessions(auth_client)
    hand_in(week10, a, '王小明', 70)
    hand_in(week12, a, '王小明 ', 60)
    hand_in(week12, a, '王小明', 81)
    hand_in(term, b, ' 陳怡君', 95)

    html = page_html(auth_client.get(f'/courses/{course}'))
    head = ' '.join(re.sub(r'<[^>]+>', ' ', re.search(r'<thead>(.*?)</thead>', html, re.S).group(1)).split())
    assert head.index('第 10 週') < head.index('第 12 週') < head.index('整學期練習')
    assert '別的課堂' not in html
    assert f'href="/class-sessions/{week12}"' in html  # a Class Session name opens its sheet
    assert sheet_rows(html) == [
        ['王小明', '70%', '81% ×2', '未作答', '未作答', '76%', '2 / 4'],
        ['陳怡君', '未作答', '未作答', '未作答', '95%', '95%', '1 / 4'],
    ]


def test_course_sheet_csv_has_a_number_and_a_take_count_per_column(auth_client):
    course, a, b, week10, week12, term = _course_with_three_sessions(auth_client)
    hand_in(week10, a, '王小明', 70)
    hand_in(week12, b, '王小明', 85)
    hand_in(week12, b, '王小明', 90)

    rows = _csv(auth_client.get(f'/courses/{course}/sheet.csv'))
    assert rows == [
        ['學生', '第 10 週 · 小考 · Timed Bank', '第 10 週 · 小考 · Timed Bank 次數',
         '第 12 週 · 小考 · Timed Bank', '第 12 週 · 小考 · Timed Bank 次數',
         '第 12 週 · 小考 · 迴圈與串列練習', '第 12 週 · 小考 · 迴圈與串列練習 次數',
         '整學期練習 · 迴圈與串列練習', '整學期練習 · 迴圈與串列練習 次數', '平均', '寫了'],
        ['王小明', '70', '1', '', '0', '90', '2', '', '0', '80', '2 / 4'],
    ]


# ---- review fix 3: Class Session and Course actions on the sheets (prototype) ----

def test_class_session_sheet_has_edit_and_end_now_with_the_shared_dialog(auth_client):
    course = make_course()
    cs = make_sheet_session(course, '第 12 週 · 小考', [(auth_client._ids['quiz_bank_id'], 20)])
    html = auth_client.get(f'/class-sessions/{cs}').get_data(as_text=True)
    assert f'data-cs-edit="{cs}"' in html
    assert f'data-cs-action="end" data-id="{cs}"' in html  # it is live
    assert 'id="cs-dialog-data"' in html
    assert 'js/class_session_actions.js' in html


def test_an_ended_class_session_sheet_offers_reopen_not_end_now(auth_client):
    course = make_course()
    cs = make_sheet_session(course, '上週', [(auth_client._ids['quiz_bank_id'], None)], starts_in_days=-7)
    html = auth_client.get(f'/class-sessions/{cs}').get_data(as_text=True)
    assert 'data-cs-action="end"' not in html
    assert f'data-cs-action="reopen" data-id="{cs}"' in html


def test_course_sheet_has_the_course_actions(auth_client):
    course = make_course()
    make_sheet_session(course, '第 12 週 · 小考', [(auth_client._ids['quiz_bank_id'], None)])
    html = auth_client.get(f'/courses/{course}').get_data(as_text=True)
    block = re.search(r'<[^>]+data-course="%d"[^>]*>' % course, html)
    assert block, 'the actions need the Course data'
    assert 'data-name="高一 3 班 · 115 上"' in block.group(0) and 'data-active="1"' in block.group(0)
    assert 'data-course-action="end"' in html and 'data-course-action="edit"' in html
    assert 'data-course-action="reopen"' not in html
    assert 'js/course_actions.js' in html

    assert auth_client.post(f'/api/courses/{course}/end', json={}).status_code == 200
    html = auth_client.get(f'/courses/{course}').get_data(as_text=True)
    assert 'data-course-action="reopen"' in html and 'data-course-action="end"' not in html
