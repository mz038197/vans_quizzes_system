"""HTTP seam: the live warning and the Class Session actions on the Quiz Bank page (ticket 11, issue #13)."""

import re

from conftest import make_class_session

WARNING = '堂課正在進行，改題目會影響正在作答的學生'


def _page(auth_client, query=''):
    response = auth_client.get(f'/quiz-bank/{auth_client._ids["quiz_bank_id"]}{query}')
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _questions_panel(html):
    return re.search(r'<section id="panel-questions".*?(?=<section id="panel-)', html, re.S).group(0)


def test_warning_shows_the_number_of_live_class_sessions(auth_client):
    ids = auth_client._ids
    make_class_session(ids, name='一')
    make_class_session(ids, name='二')
    make_class_session(ids, starts_in=3600, ends_in=7200, name='還沒')
    panel = _questions_panel(_page(auth_client))
    assert f'有 2 {WARNING}' in panel
    assert 'note-warn' in panel


def test_no_warning_without_a_live_class_session(auth_client):
    ids = auth_client._ids
    make_class_session(ids, starts_in=-7200, ends_in=-3600, name='結束了')
    make_class_session(ids, name='課程關了', course_ended=True)
    assert WARNING not in _page(auth_client)


def test_sessions_tab_rows_have_edit_delete_and_fitting_actions(auth_client):
    ids = auth_client._ids
    make_class_session(ids, name='現在')
    make_class_session(ids, starts_in=-7200, ends_in=-3600, name='剛剛')
    html = _page(auth_client, '?tab=sessions')
    rows = dict(re.findall(r'<tr data-class-session="\d+".*?class="t-title">([^<]+)<(.*?)</tr>', html, re.S))
    assert 'data-cs-action="end"' in rows['現在']
    assert 'data-cs-action="reopen"' in rows['剛剛']
    for row in rows.values():
        assert 'data-cs-edit=' in row and 'data-cs-delete=' in row
    assert '/static/js/class_session_actions.js' in html
