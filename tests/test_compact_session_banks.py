"""A Class Session with many Quiz Banks: the 儀表板 card and the 課堂 page row show a short summary,
and the details open on demand without repeating what all Quiz Banks share."""

import re
from datetime import datetime, timedelta

import app as app_module
from conftest import TEACHER_ROUTER_ID, utc8_local

CHAPTERS = ['Ch02 變數與運算', 'Ch03 條件判斷', 'Ch04 迴圈與 range', 'Ch05 串列與元組',
            'Ch06 字典', 'Ch07 函式與模組', 'Ch09 檔案與例外處理']
PREFIX = 'ITS Python 綜合演練'


def _banks(titles, folder_id=None):
    with app_module.app.app_context():
        ids = []
        for title in titles:
            bank = app_module.QuizBank(title=title, description='', teacher_id=TEACHER_ROUTER_ID,
                                       quiz_mode='fixed', folder_id=folder_id)
            app_module.db.session.add(bank)
            app_module.db.session.flush()
            ids.append(bank.id)
        app_module.db.session.commit()
        return ids


def _open(auth_client, bank_ids, limits=None, name='ITS Python 零基礎入門綜合演練'):
    now = datetime.utcnow()
    limits = limits or [None] * len(bank_ids)
    response = auth_client.post('/api/class-sessions', json={
        'new_course_name': 'ITS Python', 'name': name,
        'starts_at': utc8_local(now - timedelta(minutes=1)), 'ends_at': utc8_local(now + timedelta(hours=2)),
        'banks': [{'quiz_bank_id': b, 'time_limit_minutes': m} for b, m in zip(bank_ids, limits)],
    })
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _hand_in(class_session_id, bank_id):
    with app_module.app.app_context():
        app_module.db.session.add(app_module.Submission(
            student_name='學生甲', answers='{}', score=1, total_points=1,
            quiz_bank_id=bank_id, class_session_id=class_session_id))
        app_module.db.session.commit()


def _html(auth_client, path):
    html = auth_client.get(path).get_data(as_text=True)
    return re.sub(r'<script type="application/json" id="cs-dialog-data">.*?</script>', '', html, flags=re.S)


def _card(html, session_id):
    match = re.search(r'<article class="scard[^"]*" data-class-session="%d">.*?</article>' % session_id, html, re.S)
    assert match, 'card not found'
    return match.group(0)


def _row_and_details(html, session_id):
    """The 課堂 page row of this Class Session and the row right after it (its details), as text."""
    match = re.search(r'<tr data-class-session="%d".*?</tr>(\s*<tr class="cs-banks-row".*?</tr>)?' % session_id,
                      html, re.S)
    assert match, 'row not found'
    return match.group(0)


def _text(fragment):
    return ' '.join(re.sub(r'<[^>]+>', ' ', fragment).split())


def test_dashboard_card_sums_up_many_quiz_banks_and_names_the_shared_part_once(auth_client):
    session = _open(auth_client, _banks([f'{PREFIX}（{c}）' for c in CHAPTERS]))
    card = _card(_html(auth_client, '/teacher-dashboard'), session['id'])
    text = _text(card)
    assert '7 份題庫 · 全部不限時' in text
    assert text.count(PREFIX) == 1  # the shared part is a heading, not repeated per Quiz Bank
    for chapter in CHAPTERS:
        assert chapter in text
    assert '<details' in card  # the list opens on demand
    assert text.count('不限時') == 1


def test_dashboard_card_lists_one_or_two_quiz_banks_in_full(auth_client):
    a, b = _banks([f'{PREFIX}（Ch02 變數與運算）', f'{PREFIX}（Ch03 條件判斷）'])
    session = _open(auth_client, [a, b], limits=[20, None])
    card = _card(_html(auth_client, '/teacher-dashboard'), session['id'])
    text = _text(card)
    assert f'{PREFIX}（Ch02 變數與運算） · 時限 20 分鐘' in text
    assert f'{PREFIX}（Ch03 條件判斷） · 不限時' in text
    assert '<details' not in card


def test_class_sessions_row_has_a_one_line_summary_and_a_details_row(auth_client):
    folder = auth_client.post('/api/folders', json={'name': '高一資訊', 'color': 'blue'}).get_json()['folder']
    ids = _banks([f'{PREFIX}（{c}）' for c in CHAPTERS], folder_id=folder['id'])
    session = _open(auth_client, ids)
    _hand_in(session['id'], ids[0])
    part = _row_and_details(_html(auth_client, '/class-sessions'), session['id'])
    row, details = part.split('</tr>', 1)
    assert '7 份題庫 全部不限時 · 1 人' in _text(row)
    assert PREFIX not in _text(row)  # the row stays one line high
    assert 'aria-expanded="false"' in row and 'aria-controls=' in row
    details_text = _text(details)
    assert details_text.count(PREFIX) == 1
    assert details_text.count(folder['name']) == 1
    assert 'colspan=' in details and 'hidden' in details
    # counts differ (1 and 0), so each Quiz Bank shows its own count
    assert 'Ch02 變數與運算 · 1 人' in details_text and 'Ch03 條件判斷 · 0 人' in details_text


def test_different_time_limits_show_per_quiz_bank_and_no_shared_part_keeps_full_titles(auth_client):
    titles = ['變數小考', '迴圈練習', '函式挑戰']
    session = _open(auth_client, _banks(titles), limits=[10, 20, None])
    card_text = _text(_card(_html(auth_client, '/teacher-dashboard'), session['id']))
    assert '3 份題庫' in card_text and '全部' not in card_text
    assert '變數小考 · 10 分' in card_text and '迴圈練習 · 20 分' in card_text and '函式挑戰 · 不限時' in card_text
    part = _text(_row_and_details(_html(auth_client, '/class-sessions'), session['id']))
    assert '3 份題庫 0 人' in part



def _labels(titles):
    import bank_summary
    s = bank_summary.summarize([{'title': t, 'time_limit': None, 'n_subs': 0, 'folder': None} for t in titles])
    return s['shared'], [item['label'] for item in s['items']]


def test_shared_start_never_ends_inside_an_open_bracket():
    assert _labels(['Quiz (Ch02 a)', 'Quiz (Ch02 b)', 'Quiz (Ch03 c)']) == ('Quiz', ['Ch02 a', 'Ch02 b', 'Ch03 c'])
    assert _labels(['Quiz (Ch02 a)', 'Quiz (Ch02 b)', 'Quiz (Ch02 c)']) == ('Quiz', ['Ch02 a', 'Ch02 b', 'Ch02 c'])


def test_a_chip_drops_brackets_only_when_one_pair_wraps_its_whole_part():
    assert _labels(['測驗（Ch02 A）（進階）', '測驗（Ch03 B）', '測驗（Ch04 C）']) == (
        '測驗', ['（Ch02 A）（進階）', 'Ch03 B', 'Ch04 C'])
