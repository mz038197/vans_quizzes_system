"""HTTP seam: delete several Submissions at once (POST /api/submissions/delete).

Two ways to choose: `ids` (the Quiz Bank grades page) or `class_session_id` + `students`
(the 課堂總表: every Submission of those trimmed names in that Class Session, older Takes too).
All in one transaction: when one id is not this Teacher's, nothing is deleted.
"""

from test_grade_sheets import _bank, _course, _hand_in, _html, _rows, _session

URL = '/api/submissions/delete'


def _sheet(client, cs):
    return _rows(_html(client.get(f'/class-sessions/{cs}')))


def test_delete_by_ids_removes_those_submissions(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    cs = _session(_course(), '第 12 週 · 小考', [(bank, None)])
    a = _hand_in(cs, bank, '王小明', 70)
    b = _hand_in(cs, bank, '陳怡君', 90)
    _hand_in(cs, bank, '林冠宇', 80)

    response = auth_client.post(URL, json={'ids': [a, b]})

    assert response.status_code == 200
    assert response.get_json()['deleted'] == 2
    assert _sheet(auth_client, cs) == [['林冠宇', '80%']]


def test_one_id_of_another_teacher_deletes_nothing(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    cs = _session(_course(), '第 12 週 · 小考', [(bank, None)])
    mine = _hand_in(cs, bank, '王小明', 70)
    other_bank = _bank('別人的題庫', teacher_id=7)
    other_cs = _session(_course(teacher_id=7), '別人的課堂', [(other_bank, None)], teacher_id=7)
    theirs = _hand_in(other_cs, other_bank, '別人的學生', 50)

    response = auth_client.post(URL, json={'ids': [mine, theirs]})

    assert response.status_code == 404
    assert _sheet(auth_client, cs) == [['王小明', '70%']]


def test_an_empty_selection_is_refused(auth_client):
    response = auth_client.post(URL, json={'ids': []})

    assert response.status_code == 400
    assert response.get_json()['error'] == '沒有選擇作答'


def test_delete_students_removes_every_take_in_that_class_session_only(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    second = _bank('迴圈與串列練習')
    course = _course()
    cs = _session(course, '第 12 週 · 小考', [(bank, None), (second, None)])
    other_cs = _session(course, '第 13 週 · 小考', [(bank, None)])
    _hand_in(cs, bank, 'Vans', 0)
    _hand_in(cs, bank, ' Vans ', 10)
    _hand_in(cs, second, 'Vans', 20)
    _hand_in(cs, bank, '陳怡君', 90)
    _hand_in(other_cs, bank, 'Vans', 30)

    response = auth_client.post(URL, json={'class_session_id': cs, 'students': ['Vans']})

    assert response.get_json()['deleted'] == 3
    assert _sheet(auth_client, cs) == [['陳怡君', '90%', '未作答']]
    assert _sheet(auth_client, other_cs) == [['Vans', '30%']]


def test_delete_students_in_another_teachers_class_session_is_not_found(auth_client):
    other_bank = _bank('別人的題庫', teacher_id=7)
    other_cs = _session(_course(teacher_id=7), '別人的課堂', [(other_bank, None)], teacher_id=7)
    _hand_in(other_cs, other_bank, 'Vans', 50)

    response = auth_client.post(URL, json={'class_session_id': other_cs, 'students': ['Vans']})

    assert response.status_code == 404


def test_class_session_sheet_has_a_checkbox_for_each_student(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    course = _course()
    cs = _session(course, '第 12 週 · 小考', [(bank, None)])
    _hand_in(cs, bank, '王小明 ', 70)
    _hand_in(cs, bank, '陳怡君', 90)

    html = _html(auth_client.get(f'/class-sessions/{cs}'))

    assert 'data-select-all' in html
    assert html.count('data-student=') == 2
    assert 'data-student="王小明"' in html
    assert 'data-student=' not in _html(auth_client.get(f'/courses/{course}'))


def test_a_repeated_id_counts_once(auth_client):
    bank = auth_client._ids['quiz_bank_id']
    cs = _session(_course(), '第 12 週 · 小考', [(bank, None)])
    a = _hand_in(cs, bank, '王小明', 70)

    response = auth_client.post(URL, json={'ids': [a, a]})

    assert response.get_json()['deleted'] == 1
