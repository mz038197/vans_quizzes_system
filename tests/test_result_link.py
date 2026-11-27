"""Result Links (ADR 0008) and the startup migrations for ADRs 0007 and 0008."""
from sqlalchemy import inspect, text

import app as app_module
from conftest import TEACHER_ROUTER_ID, sign_in


def _submit(client):
    ids = client._ids
    response = client.post(
        f"/api/quiz/{ids['access_code']}/submit",
        json={'student_name': 'Alice', 'answers': {str(ids['question_id']): 'A'}},
    )
    assert response.status_code == 200
    return response.get_json()


def test_submit_returns_an_unguessable_result_link(client):
    body = _submit(client)
    token = body['result_url'].rsplit('/', 1)[-1]
    assert len(token) >= 32
    assert str(body['submission_id']) != token
    page = client.get(body['result_url'])
    assert page.status_code == 200
    assert 'Alice' in page.get_data(as_text=True)


def test_numeric_submission_id_opens_nothing(client):
    body = _submit(client)
    assert client.get(f"/result/{body['submission_id']}").status_code == 404


def test_each_submission_has_its_own_token(client):
    first = _submit(client)['result_url']
    second = _submit(client)['result_url']
    assert first != second


def test_teacher_opens_a_submission_from_the_list(auth_client):
    body = _submit(auth_client)
    url = f"/quiz-bank/{auth_client._ids['quiz_bank_id']}/submissions/{body['submission_id']}"
    page = auth_client.get(url)
    assert page.status_code == 200
    assert 'Alice' in page.get_data(as_text=True)


def test_teacher_view_needs_sign_in_and_ownership(client):
    body = _submit(client)
    url = f"/quiz-bank/{client._ids['quiz_bank_id']}/submissions/{body['submission_id']}"
    assert client.get(url).status_code == 302
    sign_in(client, TEACHER_ROUTER_ID + 1)
    response = client.get(url)
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/teacher-dashboard')


def test_teacher_view_refuses_a_submission_of_another_bank(auth_client):
    body = _submit(auth_client)
    with app_module.app.app_context():
        other = app_module.QuizBank(title='Other', access_code='OTH999', teacher_id=TEACHER_ROUTER_ID)
        app_module.db.session.add(other)
        app_module.db.session.commit()
        other_id = other.id
    assert auth_client.get(f"/quiz-bank/{other_id}/submissions/{body['submission_id']}").status_code == 404


# --- startup migrations ----------------------------------------------------

LEGACY_SCHEMA = [
    'DROP TABLE IF EXISTS submission',
    'DROP TABLE IF EXISTS question',
    'DROP TABLE IF EXISTS quiz_bank',
    'DROP TABLE IF EXISTS "user"',
    '''CREATE TABLE "user" (id INTEGER PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE,
        email VARCHAR(120) NOT NULL UNIQUE, password_hash VARCHAR(120) NOT NULL,
        is_teacher BOOLEAN, created_at DATETIME)''',
    '''CREATE TABLE quiz_bank (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, description TEXT,
        access_code VARCHAR(10) NOT NULL UNIQUE, is_active BOOLEAN, created_at DATETIME,
        teacher_id INTEGER NOT NULL, FOREIGN KEY(teacher_id) REFERENCES "user" (id))''',
    '''CREATE TABLE question (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, question_text TEXT NOT NULL,
        question_type VARCHAR(50) NOT NULL, question_data TEXT, points FLOAT, order_index INTEGER,
        quiz_bank_id INTEGER NOT NULL, created_at DATETIME, FOREIGN KEY(quiz_bank_id) REFERENCES quiz_bank (id))''',
    '''CREATE TABLE submission (id INTEGER PRIMARY KEY, student_name VARCHAR(100) NOT NULL,
        student_email VARCHAR(120), answers TEXT, score FLOAT, total_points FLOAT, submitted_at DATETIME,
        quiz_bank_id INTEGER NOT NULL, FOREIGN KEY(quiz_bank_id) REFERENCES quiz_bank (id))''',
    "INSERT INTO \"user\" (id, username, email, password_hash, is_teacher) VALUES (1, 't', 't@x', 'h', 1)",
    "INSERT INTO quiz_bank (id, title, access_code, is_active, created_at, teacher_id) VALUES (1, 'Old A', 'OLDAAA', 1, '2026-01-01 00:00:00', 1)",
    "INSERT INTO quiz_bank (id, title, access_code, is_active, created_at, teacher_id) VALUES (2, 'Old B', 'OLDBBB', 1, '2026-01-01 00:00:00', 1)",
    "INSERT INTO submission (id, student_name, answers, score, total_points, quiz_bank_id) VALUES (1, 'A', '{}', 1, 1, 1)",
    "INSERT INTO submission (id, student_name, answers, score, total_points, quiz_bank_id) VALUES (2, 'B', '{}', 1, 1, 1)",
]


def _load_legacy_database():
    app_module.db.session.remove()
    for statement in LEGACY_SCHEMA:
        app_module.db.session.execute(text(statement))
    app_module.db.session.commit()


def _scalar_rows(sql):
    return [row[0] for row in app_module.db.session.execute(text(sql)).fetchall()]


def test_legacy_submissions_get_unique_result_tokens(client):
    with app_module.app.app_context():
        _load_legacy_database()
        app_module.ensure_schema_updates()
        tokens = _scalar_rows('SELECT result_token FROM submission ORDER BY id')
        assert all(tokens) and len(set(tokens)) == 2
        app_module.ensure_schema_updates()  # safe to run again: tokens stay
        assert _scalar_rows('SELECT result_token FROM submission ORDER BY id') == tokens
        app_module.db.session.execute(text('DROP TABLE "user"'))
        app_module.db.session.commit()


def test_owner_move_waits_without_the_router_user_id(client):
    with app_module.app.app_context():
        _load_legacy_database()
        app_module.ensure_schema_updates(None)
        assert app_module.app.config['QUIZZES_OWNER_MOVE_PENDING'] is True
        assert 'user' in inspect(app_module.db.engine).get_table_names()
        assert _scalar_rows('SELECT teacher_id FROM quiz_bank') == [1, 1]

        app_module.ensure_schema_updates('not-a-number')
        assert app_module.app.config['QUIZZES_OWNER_MOVE_PENDING'] is True
        assert _scalar_rows('SELECT teacher_id FROM quiz_bank') == [1, 1]

        app_module.db.session.execute(text('DROP TABLE "user"'))
        app_module.db.session.commit()
        app_module.ensure_schema_updates(None)
    assert app_module.app.config['QUIZZES_OWNER_MOVE_PENDING'] is False


def test_owner_move_gives_every_bank_to_the_router_user_and_drops_user(client):
    with app_module.app.app_context():
        _load_legacy_database()
        app_module.ensure_schema_updates(str(TEACHER_ROUTER_ID))

        insp = inspect(app_module.db.engine)
        assert 'user' not in insp.get_table_names()
        assert app_module.app.config['QUIZZES_OWNER_MOVE_PENDING'] is False
        assert _scalar_rows('SELECT teacher_id FROM quiz_bank ORDER BY id') == [TEACHER_ROUTER_ID] * 2
        assert _scalar_rows('SELECT title FROM quiz_bank ORDER BY id') == ['Old A', 'Old B']
        assert _scalar_rows('SELECT COUNT(*) FROM submission') == [2]
        assert not [fk for fk in insp.get_foreign_keys('quiz_bank') if fk['referred_table'] == 'user']

        # The access code is still unique, and new rows insert with foreign keys on.
        app_module.db.session.execute(text('PRAGMA foreign_keys=ON'))
        app_module.db.session.execute(text(
            "INSERT INTO quiz_bank (title, access_code, is_active, created_at, teacher_id) "
            "VALUES ('New', 'NEWNEW', 1, '2026-01-01 00:00:00', 42)"
        ))
        app_module.db.session.commit()
        try:
            app_module.db.session.execute(text(
                "INSERT INTO quiz_bank (title, access_code, is_active, teacher_id) VALUES ('Dup', 'NEWNEW', 1, 42)"
            ))
            app_module.db.session.commit()
            raise AssertionError('duplicate access code was accepted')
        except Exception as error:  # noqa: BLE001
            app_module.db.session.rollback()
            assert 'UNIQUE' in str(error).upper()

        app_module.ensure_schema_updates(str(TEACHER_ROUTER_ID))  # safe to run again
        assert _scalar_rows('SELECT COUNT(*) FROM quiz_bank') == [3]

    sign_in(client, TEACHER_ROUTER_ID)
    page = client.get('/teacher-dashboard').get_data(as_text=True)
    assert 'Old A' in page and 'Old B' in page


def test_database_url_names_the_psycopg2_driver():
    assert app_module.normalize_database_url('postgres://u:p@h/db') == 'postgresql+psycopg2://u:p@h/db'
    assert app_module.normalize_database_url('postgresql://u:p@h/db') == 'postgresql+psycopg2://u:p@h/db'
    assert app_module.normalize_database_url('postgresql+psycopg2://u@h/db') == 'postgresql+psycopg2://u@h/db'
    assert app_module.normalize_database_url('sqlite:///x.db') == 'sqlite:///x.db'


def test_owner_move_that_fails_midway_changes_nothing(client, monkeypatch):
    """Code review: on SQLite the move committed the UPDATE before the rebuild and DROP."""
    real_statements = app_module.sqlite_owner_move_statements

    def failing_before_the_drop(*args, **kwargs):
        statements = real_statements(*args, **kwargs)
        return statements[:-1] + [('SELECT no_such_column FROM quiz_bank', None)] + statements[-1:]

    monkeypatch.setattr(app_module, 'sqlite_owner_move_statements', failing_before_the_drop)
    with app_module.app.app_context():
        _load_legacy_database()
        app_module.ensure_schema_updates(str(TEACHER_ROUTER_ID))

        insp = inspect(app_module.db.engine)
        assert app_module.app.config['QUIZZES_OWNER_MOVE_PENDING'] is True
        assert 'user' in insp.get_table_names()
        assert _scalar_rows('SELECT teacher_id FROM quiz_bank ORDER BY id') == [1, 1]
        assert [fk['referred_table'] for fk in insp.get_foreign_keys('quiz_bank')] == ['user']
        assert 'quiz_bank__owner_mig' not in insp.get_table_names()

        monkeypatch.setattr(app_module, 'sqlite_owner_move_statements', real_statements)
        app_module.ensure_schema_updates(str(TEACHER_ROUTER_ID))  # the next start completes it
        assert _scalar_rows('SELECT teacher_id FROM quiz_bank ORDER BY id') == [TEACHER_ROUTER_ID] * 2
        assert app_module.app.config['QUIZZES_OWNER_MOVE_PENDING'] is False


def test_owner_move_leaves_teacher_id_indexed_and_one_token_index(client):
    with app_module.app.app_context():
        _load_legacy_database()
        app_module.ensure_schema_updates(str(TEACHER_ROUTER_ID))
        insp = inspect(app_module.db.engine)
        bank_indexes = {tuple(ix['column_names']) for ix in insp.get_indexes('quiz_bank')}
        assert ('teacher_id',) in bank_indexes
        token_indexes = [ix for ix in insp.get_indexes('submission') if ix['column_names'] == ['result_token']]
        token_constraints = [uc for uc in insp.get_unique_constraints('submission')
                             if uc['column_names'] == ['result_token']]
        assert len(token_indexes) + len(token_constraints) == 1


def test_new_database_has_one_unique_rule_on_result_token(client):
    with app_module.app.app_context():
        insp = inspect(app_module.db.engine)
        token_indexes = [ix for ix in insp.get_indexes('submission') if ix['column_names'] == ['result_token']]
        token_constraints = [uc for uc in insp.get_unique_constraints('submission')
                             if uc['column_names'] == ['result_token']]
        assert len(token_indexes) + len(token_constraints) == 1
