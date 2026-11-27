"""HTTP seam: the Quiz Bank 成績 page features (ticket 15, #17).

Statistics, score bands, most missed, repeat-Take numbering, 時間到 and the CSV export,
all through the Flask test client. Students hand in through the Class Session code.
"""

import csv
import io

import pytest

BOM = chr(0xFEFF)

import app as app_module
from conftest import make_class_session


@pytest.fixture
def bank(auth_client):
    """The fixture Quiz Bank with five single-choice questions (1 point each, answer 'A')."""
    ids = auth_client._ids
    with app_module.app.app_context():
        for i in range(2, 6):
            app_module.db.session.add(app_module.Question(
                title=f'Q{i}', question_text='What?', question_type='single_choice',
                question_data='{"options": ["A", "B"], "correct_answer": "A"}',
                points=1, order_index=i - 1, quiz_bank_id=ids['quiz_bank_id'],
            ))
        app_module.db.session.commit()
        questions = (app_module.Question.query.filter_by(quiz_bank_id=ids['quiz_bank_id'])
                     .order_by(app_module.Question.order_index).all())
        ids['question_ids'] = [q.id for q in questions]
    return auth_client


def hand_in(client, code, name, right, elapsed=None, email=''):
    """Hand in with the first `right` questions answered right and the rest wrong."""
    qids = client._ids['question_ids']
    answers = {str(q): ('A' if i < right else 'B') for i, q in enumerate(qids)}
    body = {'student_name': name, 'student_email': email, 'answers': answers,
            'quiz_bank_id': client._ids['quiz_bank_id']}
    if elapsed is not None:
        body['elapsed_seconds'] = elapsed
    response = client.post(f'/api/quiz/{code}/submit', json=body)
    assert response.status_code == 200, response.get_json()
    return response.get_json()['submission_id']


def session_id(code):
    with app_module.app.app_context():
        return app_module.ClassSession.query.filter_by(code=code).one().id


def grades(client, **params):
    qb = client._ids['quiz_bank_id']
    response = client.get(f'/api/quiz-bank/{qb}/grades', query_string=params)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_statistics_for_all_class_sessions_and_for_one(bank):
    a = make_class_session(bank._ids, name='一班')
    b = make_class_session(bank._ids, name='二班')
    hand_in(bank, a, '學生甲', 5)   # 100
    hand_in(bank, a, '學生乙', 4)   # 80
    hand_in(bank, a, '學生甲 ', 2)  # 40, same trimmed name
    hand_in(bank, b, '學生丙', 3)   # 60
    hand_in(bank, b, '學生丁', 1)   # 20

    stats = grades(bank)['stats']
    assert stats['count'] == 5
    assert stats['students'] == 4
    assert stats['average'] == 60
    assert stats['median'] == 60
    assert stats['highest'] == 100
    assert stats['lowest'] == 20
    assert stats['passed'] == 3
    assert stats['pass_rate'] == 60

    one = grades(bank, class_session=session_id(a))['stats']
    assert one['count'] == 3
    assert one['students'] == 2
    assert one['average'] == pytest.approx(220 / 3)
    assert one['median'] == 80
    assert one['highest'] == 100
    assert one['lowest'] == 40
    assert one['passed'] == 2
    assert one['pass_rate'] == pytest.approx(200 / 3)

    two = grades(bank, class_session=session_id(b))['stats']
    assert two['count'] == 2
    assert two['median'] == 40  # even count: mean of the middle two
    assert two['pass_rate'] == 50


def test_statistics_with_no_submission_are_empty(bank):
    data = grades(bank)
    assert data['stats']['count'] == 0
    assert data['stats']['average'] is None
    assert data['submissions'] == []


def test_filter_lists_the_class_sessions_with_their_status(bank):
    live = make_class_session(bank._ids, name='一班')
    make_class_session(bank._ids, name='三班', starts_in=3600, ends_in=7200)
    options = grades(bank)['class_sessions']
    by_name = {o['name']: o for o in options}
    assert by_name['一班']['status'] == 'live'
    assert by_name['一班']['status_label'] == '進行中'
    assert by_name['一班']['id'] == session_id(live)
    assert by_name['三班']['status_label'] == '即將開始'


def test_unknown_or_foreign_class_session_is_not_found(bank):
    foreign = make_class_session(bank._ids, name='別人的', teacher_id=999)
    qb = bank._ids['quiz_bank_id']
    assert bank.get(f'/api/quiz-bank/{qb}/grades?class_session=99999').status_code == 404
    assert bank.get(f'/api/quiz-bank/{qb}/grades?class_session={session_id(foreign)}').status_code == 404


def test_score_bands(bank):
    a = make_class_session(bank._ids, name='一班')
    b = make_class_session(bank._ids, name='二班')
    for right in (5, 5, 4, 3, 3, 0):  # 100 100 80 60 60 0
        hand_in(bank, a, '甲', right)
    hand_in(bank, b, '乙', 2)  # 40

    bands = grades(bank)['bands']
    assert [(x['label'], x['count']) for x in bands] == [
        ('90–100', 2), ('80–89', 1), ('70–79', 0), ('60–69', 2), ('0–59', 2),
    ]
    one = grades(bank, class_session=session_id(b))['bands']
    assert [x['count'] for x in one] == [0, 0, 0, 0, 1]


def test_most_missed_uses_the_result_page_judgement(bank):
    a = make_class_session(bank._ids, name='一班')
    b = make_class_session(bank._ids, name='二班')
    qids = bank._ids['question_ids']
    hand_in(bank, a, '甲', 3)  # misses Q4 Q5
    hand_in(bank, a, '乙', 4)  # misses Q5
    hand_in(bank, b, '丙', 5)  # misses none

    missed = grades(bank)['most_missed']
    assert [(m['question_id'], m['number'], m['wrong'], m['seen']) for m in missed] == [
        (qids[4], 5, 2, 3), (qids[3], 4, 1, 3),
    ]
    assert missed[0]['question_type'] == 'single_choice'
    assert missed[0]['wrong_rate'] == pytest.approx(200 / 3)

    one = grades(bank, class_session=session_id(a))['most_missed']
    assert [(m['number'], m['wrong_rate']) for m in one] == [(5, 100), (4, 50)]
    assert grades(bank, class_session=session_id(b))['most_missed'] == []


def test_most_missed_counts_a_blank_answer_as_wrong(bank):
    a = make_class_session(bank._ids, name='一班')
    qids = bank._ids['question_ids']
    response = bank.post(f'/api/quiz/{a}/submit', json={
        'student_name': '甲', 'answers': {str(q): 'A' for q in qids[:4]}, 'quiz_bank_id': bank._ids['quiz_bank_id'],
    })
    assert response.status_code == 200
    assert [m['number'] for m in grades(bank)['most_missed']] == [5]


def test_repeat_takes_are_numbered_per_trimmed_name_class_session_and_quiz_bank(bank):
    a = make_class_session(bank._ids, name='一班')
    b = make_class_session(bank._ids, name='二班')
    first = hand_in(bank, a, '學生甲', 1)
    other = hand_in(bank, a, '學生乙', 1)
    second = hand_in(bank, a, ' 學生甲 ', 5)
    elsewhere = hand_in(bank, b, '學生甲', 3)
    third = hand_in(bank, a, '學生甲', 2)

    rows = {r['id']: r for r in grades(bank)['submissions']}
    assert (rows[first]['take'], rows[first]['takes']) == (1, 3)
    assert (rows[second]['take'], rows[second]['takes']) == (2, 3)
    assert (rows[third]['take'], rows[third]['takes']) == (3, 3)
    assert (rows[other]['take'], rows[other]['takes']) == (1, 1)
    assert (rows[elsewhere]['take'], rows[elsewhere]['takes']) == (1, 1)

    # The number does not change with the filter.
    rows_a = {r['id']: r for r in grades(bank, class_session=session_id(a))['submissions']}
    assert rows_a[third]['take'] == 3
    assert elsewhere not in rows_a


def test_rows_show_class_session_rank_and_time_up(bank):
    timed = make_class_session(bank._ids, name='一班', time_limit=10)
    open_ended = make_class_session(bank._ids, name='二班')
    up = hand_in(bank, timed, '甲', 2, elapsed=600)
    early = hand_in(bank, timed, '乙', 5, elapsed=599)
    untimed = hand_in(bank, open_ended, '丙', 4, elapsed=5000)

    rows = grades(bank)['submissions']
    assert [r['id'] for r in rows] == [early, untimed, up]  # by score, highest first
    assert [r['rank'] for r in rows] == [1, 2, 3]
    by_id = {r['id']: r for r in rows}
    assert by_id[up]['time_up'] is True
    assert by_id[early]['time_up'] is False
    assert by_id[untimed]['time_up'] is False
    assert by_id[up]['class_session'] == '一班'
    assert by_id[untimed]['class_session'] == '二班'


def test_search_by_name_filters_the_rows_but_not_the_statistics(bank):
    a = make_class_session(bank._ids, name='一班')
    hand_in(bank, a, '王小明', 5)
    hand_in(bank, a, '李大華', 2)
    data = grades(bank, q=' 小明')
    assert [r['student_name'] for r in data['submissions']] == ['王小明']
    assert data['stats']['count'] == 2


def _csv(client, **params):
    qb = client._ids['quiz_bank_id']
    response = client.get(f'/quiz-bank/{qb}/submissions.csv', query_string=params)
    assert response.status_code == 200
    assert response.mimetype == 'text/csv'
    text = response.get_data(as_text=True)
    assert text.startswith(BOM)
    return list(csv.reader(io.StringIO(text.lstrip(BOM))))


def test_csv_holds_only_the_filtered_submissions(bank):
    a = make_class_session(bank._ids, name='一班', time_limit=10)
    b = make_class_session(bank._ids, name='二班')
    hand_in(bank, a, '學生甲', 5, elapsed=125, email='a@example.com')
    hand_in(bank, a, '學生甲', 2, elapsed=600)
    hand_in(bank, b, '學生乙', 4)

    rows = _csv(bank)
    header, body = rows[0], rows[1:]
    assert header == ['名次', '姓名', 'Email', '課堂', '第幾次', '得分', '總分', '百分比', '用時', '時間到', '交卷時間']
    assert [r[1] for r in body] == ['學生甲', '學生乙', '學生甲']

    only_a = _csv(bank, class_session=session_id(a))[1:]
    assert [(r[0], r[1], r[3], r[4], r[5], r[7], r[8], r[9]) for r in only_a] == [
        ('1', '學生甲', '一班', '1', '5', '100.0', '2:05', ''),
        ('2', '學生甲', '一班', '2', '2', '40.0', '10:00', '時間到'),
    ]
    assert only_a[0][2] == 'a@example.com'

    searched = _csv(bank, q='學生乙')[1:]
    assert [r[1] for r in searched] == ['學生乙']


def test_csv_and_api_need_the_owner(bank):
    qb = bank._ids['quiz_bank_id']
    from conftest import sign_in
    sign_in(bank, 7)
    assert bank.get(f'/api/quiz-bank/{qb}/grades').status_code == 403
    assert bank.get(f'/quiz-bank/{qb}/submissions.csv').status_code in (302, 403)
