"""Folders on the 題庫 page, driven through the HTTP routes (spec #2, issue #9, ADR 0009)."""

import io

import app as app_module
from conftest import OWN_ORIGIN, TEACHER_ROUTER_ID, ended_class_session_id, sign_in


def _create_folder(client, name, color='blue'):
    return client.post('/api/folders', json={'name': name, 'color': color})


def _folder_id(client, name, color='blue'):
    response = _create_folder(client, name, color)
    assert response.status_code == 201, response.get_json()
    return response.get_json()['folder']['id']


def _bank_folder(bank_id):
    with app_module.app.app_context():
        return app_module.db.session.get(app_module.QuizBank, bank_id).folder_id


def _move(client, bank_ids, folder_id):
    return client.post('/api/quiz-banks/move', json={'quiz_bank_ids': bank_ids, 'folder_id': folder_id})


def _other_teacher(client):
    sign_in(client, TEACHER_ROUTER_ID + 1, name='別的老師')
    client.environ_base['HTTP_ORIGIN'] = OWN_ORIGIN


def _bank(title, teacher_id=TEACHER_ROUTER_ID):
    with app_module.app.app_context():
        bank = app_module.QuizBank(title=title, description='',
                                   teacher_id=teacher_id, quiz_mode='fixed')
        app_module.db.session.add(bank)
        app_module.db.session.commit()
        return bank.id


# --- create ---------------------------------------------------------------

def test_create_folder_shows_it_on_the_quiz_banks_page(auth_client):
    response = _create_folder(auth_client, '  七年級數學 ', 'green')

    assert response.status_code == 201
    folder = response.get_json()['folder']
    assert folder['name'] == '七年級數學'
    assert folder['color'] == 'green'
    page = auth_client.get('/quiz-banks').get_data(as_text=True)
    assert '七年級數學' in page
    assert 'fc-green' in page


def test_create_folder_with_blank_name_is_refused(auth_client):
    response = _create_folder(auth_client, '   ')

    assert response.status_code == 400
    assert '名稱' in response.get_json()['error']


def test_create_folder_with_a_used_name_is_refused(auth_client):
    _folder_id(auth_client, '八年級')

    response = _create_folder(auth_client, ' 八年級 ', 'pink')

    assert response.status_code == 400
    assert '已經有' in response.get_json()['error']


def test_another_teacher_may_use_the_same_folder_name(auth_client):
    _folder_id(auth_client, '八年級')
    _other_teacher(auth_client)

    assert _create_folder(auth_client, '八年級').status_code == 201


def test_create_folder_with_an_unknown_color_is_refused(auth_client):
    assert _create_folder(auth_client, '九年級', 'orange').status_code == 400


# --- rename and recolour ----------------------------------------------------

def test_rename_and_recolour_folder(auth_client):
    folder_id = _folder_id(auth_client, '舊名', 'blue')

    response = auth_client.put(f'/api/folders/{folder_id}', json={'name': '新名', 'color': 'amber'})

    assert response.status_code == 200
    assert response.get_json()['folder'] == {'id': folder_id, 'name': '新名', 'color': 'amber', 'cover_url': None}
    page = auth_client.get('/quiz-banks').get_data(as_text=True)
    assert '新名' in page and '舊名' not in page
    assert 'fc-amber' in page


def test_rename_folder_to_a_used_name_is_refused(auth_client):
    _folder_id(auth_client, '甲')
    folder_id = _folder_id(auth_client, '乙')

    response = auth_client.put(f'/api/folders/{folder_id}', json={'name': '甲', 'color': 'blue'})

    assert response.status_code == 400
    with app_module.app.app_context():
        assert app_module.db.session.get(app_module.Folder, folder_id).name == '乙'


def test_rename_folder_keeping_its_name_changes_only_the_colour(auth_client):
    folder_id = _folder_id(auth_client, '甲', 'blue')

    response = auth_client.put(f'/api/folders/{folder_id}', json={'name': '甲', 'color': 'cyan'})

    assert response.status_code == 200
    assert response.get_json()['folder']['color'] == 'cyan'


# --- delete -------------------------------------------------------------------

def test_delete_folder_moves_its_quiz_banks_to_unsorted_and_keeps_them(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    folder_id = _folder_id(auth_client, '要刪的')
    assert _move(auth_client, [bank_id], folder_id).status_code == 200
    with app_module.app.app_context():
        app_module.db.session.add(app_module.Submission(
            student_name='學生甲', answers='{}', score=1, total_points=1, quiz_bank_id=bank_id,
            class_session_id=ended_class_session_id(bank_id)))
        app_module.db.session.commit()

    response = auth_client.delete(f'/api/folders/{folder_id}')

    assert response.status_code == 200
    with app_module.app.app_context():
        assert app_module.db.session.get(app_module.Folder, folder_id) is None
        bank = app_module.db.session.get(app_module.QuizBank, bank_id)
        assert bank is not None and bank.folder_id is None
        assert len(bank.questions) == 1
        assert app_module.Submission.query.filter_by(quiz_bank_id=bank_id).count() == 1
    page = auth_client.get('/quiz-banks').get_data(as_text=True)
    assert 'Timed Bank' in page


# --- move ---------------------------------------------------------------------

def test_move_quiz_bank_into_folder_and_back_to_unsorted(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    folder_id = _folder_id(auth_client, '七年級')

    assert _move(auth_client, [bank_id], folder_id).status_code == 200
    assert _bank_folder(bank_id) == folder_id
    inside = auth_client.get(f'/quiz-banks?folder={folder_id}').get_data(as_text=True)
    assert 'Timed Bank' in inside
    unsorted = auth_client.get('/quiz-banks').get_data(as_text=True)
    assert f'data-bank="{bank_id}"' not in unsorted

    assert _move(auth_client, [bank_id], None).status_code == 200
    assert _bank_folder(bank_id) is None
    assert f'data-bank="{bank_id}"' in auth_client.get('/quiz-banks').get_data(as_text=True)


def test_move_many_quiz_banks_at_once(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second = _bank('Second')
    folder_id = _folder_id(auth_client, '七年級')

    response = _move(auth_client, [first, second], folder_id)

    assert response.status_code == 200
    assert response.get_json()['moved'] == 2
    assert _bank_folder(first) == folder_id and _bank_folder(second) == folder_id


def test_move_is_all_or_nothing_when_one_quiz_bank_is_not_yours(auth_client):
    mine = auth_client._ids['quiz_bank_id']
    theirs = _bank('Theirs', teacher_id=TEACHER_ROUTER_ID + 1)
    folder_id = _folder_id(auth_client, '七年級')

    response = _move(auth_client, [mine, theirs], folder_id)

    assert response.status_code == 404
    assert _bank_folder(mine) is None and _bank_folder(theirs) is None


def test_move_into_another_teachers_folder_is_refused(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    _other_teacher(auth_client)
    their_folder = _folder_id(auth_client, '別人的')
    sign_in(auth_client, TEACHER_ROUTER_ID)

    assert _move(auth_client, [bank_id], their_folder).status_code == 404
    assert _bank_folder(bank_id) is None


def test_another_teacher_cannot_rename_or_delete_my_folder(auth_client):
    folder_id = _folder_id(auth_client, '我的')
    _other_teacher(auth_client)

    assert auth_client.put(f'/api/folders/{folder_id}', json={'name': 'x', 'color': 'blue'}).status_code == 404
    assert auth_client.delete(f'/api/folders/{folder_id}').status_code == 404
    assert auth_client.get(f'/quiz-banks?folder={folder_id}').status_code in (302, 404)
    with app_module.app.app_context():
        assert app_module.db.session.get(app_module.Folder, folder_id).name == '我的'


def test_folder_writes_need_own_origin(auth_client):
    auth_client.environ_base['HTTP_ORIGIN'] = 'https://evil.example'

    assert _create_folder(auth_client, '甲').status_code == 403


# --- 題庫 page -----------------------------------------------------------------

def test_folder_card_shows_count_and_attention(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    folder_id = _folder_id(auth_client, '七年級')
    _move(auth_client, [bank_id], folder_id)
    with app_module.app.app_context():
        app_module.db.session.add(app_module.Submission(
            student_name='學生甲', answers='{}', score=0, total_points=1, quiz_bank_id=bank_id,
            class_session_id=ended_class_session_id(bank_id)))
        app_module.db.session.commit()

    page = auth_client.get('/quiz-banks').get_data(as_text=True)

    card = page[page.index(f'data-folder="{folder_id}"'):]
    card = card[:card.index('</a>')]
    assert '1 個題庫' in card
    assert '1 個需要注意' in card


def test_folder_view_has_breadcrumb_and_other_folder_chips(auth_client):
    bank_id = auth_client._ids['quiz_bank_id']
    folder_id = _folder_id(auth_client, '七年級')
    _folder_id(auth_client, '八年級')
    _move(auth_client, [bank_id], folder_id)

    page = auth_client.get(f'/quiz-banks?folder={folder_id}').get_data(as_text=True)

    crumbs = page[page.index('class="crumbs"'):]
    crumbs = crumbs[:crumbs.index('</nav>')]
    assert '題庫' in crumbs and '七年級' in crumbs
    assert '八年級' in page
    assert f'/create-quiz-bank?folder={folder_id}' in page


# --- create a Quiz Bank inside a Folder ---------------------------------------

def test_quiz_bank_created_in_a_folder_belongs_to_it(auth_client):
    folder_id = _folder_id(auth_client, '七年級')

    response = auth_client.post('/create-quiz-bank', json={'title': '新題庫', 'folder_id': folder_id})

    assert response.status_code == 200
    assert _bank_folder(response.get_json()['quiz_bank_id']) == folder_id


def test_quiz_bank_created_without_folder_is_unsorted(auth_client):
    response = auth_client.post('/create-quiz-bank', json={'title': '新題庫'})

    assert _bank_folder(response.get_json()['quiz_bank_id']) is None


def test_quiz_bank_cannot_be_created_in_another_teachers_folder(auth_client):
    _other_teacher(auth_client)
    their_folder = _folder_id(auth_client, '別人的')
    sign_in(auth_client, TEACHER_ROUTER_ID)

    response = auth_client.post('/create-quiz-bank', json={'title': '新題庫', 'folder_id': their_folder})

    assert response.status_code == 404
    with app_module.app.app_context():
        assert app_module.QuizBank.query.filter_by(title='新題庫').count() == 0


MD_BANK = """---
title: 匯入的題庫
---

---
title: 加法
type: single_choice
points: 1
---

1 + 1 = ?

options:
  - 1
  - 2
correct_answer: 2
"""


def test_markdown_import_in_a_folder_belongs_to_it(auth_client):
    folder_id = _folder_id(auth_client, '七年級')

    response = auth_client.post('/api/import-quiz-md/confirm', data={
        'file': (io.BytesIO(MD_BANK.encode('utf-8')), 'bank.md'),
        'folder_id': str(folder_id),
    }, content_type='multipart/form-data')

    assert response.status_code == 200, response.get_json()
    assert _bank_folder(response.get_json()['quiz_bank_id']) == folder_id


def test_create_page_keeps_the_folder(auth_client):
    folder_id = _folder_id(auth_client, '七年級')

    page = auth_client.get(f'/create-quiz-bank?folder={folder_id}').get_data(as_text=True)

    assert '七年級' in page
    assert f'data-folder-id="{folder_id}"' in page


# --- search across all Folders (issue #10) ------------------------------------

def _rows(page):
    """The Quiz Bank rows of the 題庫 table, as {bank id: row html}."""
    body = page[page.index('<tbody'):page.index('</tbody>')] if '<tbody' in page else ''
    rows = {}
    for chunk in body.split('<tr')[1:]:
        if 'data-bank="' in chunk:
            bank_id = int(chunk.split('data-bank="', 1)[1].split('"', 1)[0])
            rows[bank_id] = chunk
    return rows


def test_search_finds_quiz_banks_inside_folders_and_shows_their_folder(auth_client):
    inside = _bank('分數加法')
    unsorted = _bank('分數乘法')
    _bank('幾何圖形')
    folder_id = _folder_id(auth_client, '七年級', 'green')
    _move(auth_client, [inside], folder_id)

    page = auth_client.get('/quiz-banks?q=分數').get_data(as_text=True)

    rows = _rows(page)
    assert set(rows) == {inside, unsorted}
    assert '七年級' in rows[inside]
    assert '未分類' in rows[unsorted]
    assert '資料夾</th>' in page


def test_search_matches_the_description_and_ignores_case(auth_client):
    by_title = auth_client._ids['quiz_bank_id']  # 'Timed Bank'
    by_description = _bank('第三章')
    _bank('第四章')
    with app_module.app.app_context():
        app_module.db.session.get(app_module.QuizBank, by_description).description = 'TIMED review'
        app_module.db.session.commit()

    page = auth_client.get('/quiz-banks?q=timed').get_data(as_text=True)

    assert set(_rows(page)) == {by_title, by_description}


def test_search_does_not_show_another_teachers_quiz_banks(auth_client):
    _bank('分數別人的', teacher_id=TEACHER_ROUTER_ID + 1)

    page = auth_client.get('/quiz-banks?q=分數').get_data(as_text=True)

    assert _rows(page) == {}
    assert '找不到' in page


def test_search_inside_a_folder_view_still_searches_every_folder(auth_client):
    first = _bank('分數加法')
    second = _bank('分數乘法')
    seventh = _folder_id(auth_client, '七年級')
    eighth = _folder_id(auth_client, '八年級')
    _move(auth_client, [first], seventh)
    _move(auth_client, [second], eighth)

    page = auth_client.get(f'/quiz-banks?folder={seventh}&q=分數').get_data(as_text=True)

    assert set(_rows(page)) == {first, second}


# --- move answers what moved, for 復原 (issue #10) -----------------------------

def test_move_answers_where_each_quiz_bank_was_so_it_can_be_undone(auth_client):
    first = auth_client._ids['quiz_bank_id']
    second = _bank('Second')
    seventh = _folder_id(auth_client, '七年級')
    eighth = _folder_id(auth_client, '八年級')
    _move(auth_client, [second], seventh)

    response = _move(auth_client, [first, second], eighth)

    previous = {p['id']: p['folder_id'] for p in response.get_json()['previous']}
    assert previous == {first: None, second: seventh}
    for folder_id in {None, seventh}:
        ids = [i for i, f in previous.items() if f == folder_id]
        assert _move(auth_client, ids, folder_id).status_code == 200
    assert _bank_folder(first) is None and _bank_folder(second) == seventh


def test_move_with_an_unknown_quiz_bank_moves_nothing(auth_client):
    mine = auth_client._ids['quiz_bank_id']
    folder_id = _folder_id(auth_client, '七年級')

    assert _move(auth_client, [mine, 999999], folder_id).status_code == 404
    assert _bank_folder(mine) is None
