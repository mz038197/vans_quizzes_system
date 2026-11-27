"""HTTP seam: the 課堂 page, grouped by Course, with status tabs, search and sort (ticket 11, issue #13)."""

import re

import app as app_module
from conftest import TEACHER_ROUTER_ID, make_class_session


def _page(auth_client, query=''):
    response = auth_client.get('/class-sessions' + query)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _open_part(html):
    """The page without the folded 已結束的課程 part."""
    return html.split('id="ended-courses"')[0]


def _ended_part(html):
    parts = html.split('id="ended-courses"')
    return parts[1] if len(parts) > 1 else ''


def _names(html):
    return re.findall(r'<tr data-class-session="\d+".*?class="t-title">([^<]+)<', html, re.S)


def _course_id(code):
    with app_module.app.app_context():
        return app_module.ClassSession.query.filter_by(code=code).one().course_id


def _move_to_course(code, course_id):
    with app_module.app.app_context():
        row = app_module.ClassSession.query.filter_by(code=code).one()
        row.course_id = course_id
        app_module.db.session.commit()


def test_nav_shows_the_sessions_area_as_active(auth_client):
    html = _page(auth_client)
    assert re.search(r'<a [^>]*href="/class-sessions"[^>]*aria-current="page"', html)
    assert '/static/js/class_session_dialog.js' in html  # 開課堂 works here
    assert '新課程' in html


def test_class_sessions_are_sorted_live_then_soonest_upcoming_then_latest_ended(auth_client):
    ids = auth_client._ids
    first = make_class_session(ids, starts_in=-7200, ends_in=-5400, name='很久以前')
    course_id = _course_id(first)
    for starts_in, ends_in, name in [
        (7200, 9000, '後天'), (-600, 2400, '現在'), (-3600, -1800, '剛剛'), (3600, 5400, '等一下'),
    ]:
        _move_to_course(make_class_session(ids, starts_in=starts_in, ends_in=ends_in, name=name), course_id)
    assert _names(_page(auth_client)) == ['現在', '等一下', '後天', '剛剛', '很久以前']


def test_status_tabs_filter_and_show_counts(auth_client):
    ids = auth_client._ids
    make_class_session(ids, starts_in=-600, ends_in=2400, name='進行的')
    make_class_session(ids, starts_in=3600, ends_in=7200, name='還沒的')
    make_class_session(ids, starts_in=-7200, ends_in=-3600, name='結束的')
    html = _page(auth_client)
    counts = dict(re.findall(r'data-status="(\w+)"[^>]*>[^<]*<span class="cnt">(\d+)</span>', html))
    assert counts == {'all': '3', 'live': '1', 'soon': '1', 'done': '1'}
    assert _names(_page(auth_client, '?status=live')) == ['進行的']
    assert _names(_page(auth_client, '?status=soon')) == ['還沒的']
    assert _names(_page(auth_client, '?status=done')) == ['結束的']
    assert re.search(r'data-status="live"[^>]*aria-current="page"', _page(auth_client, '?status=live'))


def test_search_matches_course_class_session_quiz_bank_and_code(auth_client):
    ids = auth_client._ids
    a = make_class_session(ids, name='期中考')
    make_class_session(ids, name='小考')
    assert _names(_page(auth_client, '?q=期中')) == ['期中考']
    assert _names(_page(auth_client, '?q=' + a.lower())) == ['期中考']
    assert _names(_page(auth_client, '?q=期中考 的課程')) == ['期中考']  # Course name
    assert sorted(_names(_page(auth_client, '?q=timed'))) == ['小考', '期中考']  # Quiz Bank title
    assert '找不到符合的課堂' in _page(auth_client, '?q=沒有這個')


def test_course_block_shows_name_status_end_and_count_with_actions(auth_client):
    code = make_class_session(auth_client._ids, name='第一堂', course_ends_in=30 * 86400)
    course_id = _course_id(code)
    html = _open_part(_page(auth_client))
    block = re.search(rf'<section class="panel crs" data-course="{course_id}".*?</section>', html, re.S).group(0)
    assert '第一堂 的課程' in block
    assert 'class="sp live"' in block
    assert '23:59' in block
    assert '1 個課堂' in block
    assert f'data-open-session="" data-course="{course_id}"' in block
    assert 'data-course-action="end"' in block
    assert 'data-course-action="edit"' in block
    assert 'data-course-action="delete"' in block


def test_ended_courses_are_folded_and_their_sessions_say_why(auth_client):
    ids = auth_client._ids
    make_class_session(ids, name='開著的')
    make_class_session(ids, starts_in=3600, ends_in=7200, name='關掉的', course_ended=True)
    html = _page(auth_client)
    assert '已結束的課程（1）' in html
    assert _names(_open_part(html)) == ['開著的']
    ended = _ended_part(html)
    assert _names(ended) == ['關掉的']
    assert '已結束（課程已結束）' in ended
    assert 'data-course-action="reopen"' in ended
    for action in ('start-now', 'extend', 'reopen"'):
        assert f'data-cs-action="{action}' not in ended
    # the tab counts cover open Courses only
    counts = dict(re.findall(r'data-status="(\w+)"[^>]*>[^<]*<span class="cnt">(\d+)</span>', html))
    assert counts['all'] == '1'


def test_row_shows_code_banks_with_time_limit_count_and_folder_and_fitting_actions(auth_client):
    ids = auth_client._ids
    folder = auth_client.post('/api/folders', json={'name': '一年級', 'color': 'green'}).get_json()['folder']
    auth_client.post('/api/quiz-banks/move', json={'quiz_bank_ids': [ids['quiz_bank_id']], 'folder_id': folder['id']})
    live = make_class_session(ids, name='現在', time_limit=20)
    make_class_session(ids, starts_in=3600, ends_in=7200, name='等一下')
    make_class_session(ids, starts_in=-7200, ends_in=-3600, name='剛剛')
    auth_client.post(f'/api/quiz/{live}/submit', json={
        'student_name': 'Student A', 'quiz_bank_id': ids['quiz_bank_id'],
        'answers': {str(ids['question_id']): 'A'}, 'elapsed_seconds': 5})
    html = _page(auth_client)
    rows = dict(re.findall(r'<tr data-class-session="\d+".*?class="t-title">([^<]+)<(.*?)</tr>', html, re.S))
    assert f'<span class="code">{live}</span>' in rows['現在']
    assert 'Timed Bank' in rows['現在'] and '時限 20 分鐘' in rows['現在'] and '1 人' in rows['現在']
    assert '一年級' in rows['現在']
    assert 'data-cs-action="end"' in rows['現在']
    assert 'data-cs-action="start-now"' in rows['等一下']
    assert 'data-cs-action="extend"' in rows['現在']
    assert 'data-cs-action="extend"' not in rows['等一下']  # only a live one can be extended
    assert 'data-cs-action="reopen"' in rows['剛剛']
    assert 'data-cs-action="end"' not in rows['剛剛']
    for row in rows.values():
        assert 'data-cs-edit=' in row and 'data-cs-delete=' in row


def test_empty_page_asks_for_a_course_first(auth_client):
    assert '還沒有課程' in _page(auth_client)


def test_page_shows_only_this_teachers_courses(auth_client):
    make_class_session(auth_client._ids, name='別人的', teacher_id=TEACHER_ROUTER_ID + 1)
    html = _page(auth_client)
    assert '別人的' not in html


def test_page_needs_a_signed_in_teacher(client):
    response = client.get('/class-sessions')
    assert response.status_code == 302


def test_live_and_upcoming_rows_have_a_projector_qr_button(auth_client):
    """Review fix 4: the 投影 QR button of the dashboard cards, on the 課堂 page rows."""
    ids = auth_client._ids
    live = make_class_session(ids, name='現在')
    soon = make_class_session(ids, starts_in=3600, ends_in=7200, name='等一下')
    done = make_class_session(ids, starts_in=-7200, ends_in=-3600, name='剛剛')
    html = _page(auth_client)
    rows = dict(re.findall(r'<tr data-class-session="\d+".*?class="t-title">([^<]+)<(.*?)</tr>', html, re.S))
    assert f'data-qr="{live}"' in rows['現在']
    assert f'data-qr="{soon}"' in rows['等一下']
    assert f'data-qr="{done}"' not in rows['剛剛']
    assert 'id="qr-stage"' in html
    assert '/static/js/vendor/qrcode.js' in html and '/static/js/qr_stage.js' in html
