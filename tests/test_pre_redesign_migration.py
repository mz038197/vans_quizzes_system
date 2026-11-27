"""Issue #16: an old database (schema as on main before the redesign) moves its Submissions into
one ended 「改版前」 Course per Teacher, with one 「改版前的作答」 Class Session per Quiz Bank."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect, text

from conftest import OWN_ORIGIN, app_module, sign_in

# The exact DDL that db.create_all() made on main (ecbb9cc), before Folders and Class Sessions.
OLD_SCHEMA = [
    """CREATE TABLE quiz_bank (
        id INTEGER NOT NULL, title VARCHAR(200) NOT NULL, description TEXT,
        access_code VARCHAR(10) NOT NULL, is_active BOOLEAN, quiz_mode VARCHAR(20),
        session_question_count INTEGER, category_ratios TEXT, scoring_mode VARCHAR(20),
        scoring_total_points FLOAT, time_limit_minutes INTEGER, created_at DATETIME,
        teacher_id INTEGER NOT NULL, PRIMARY KEY (id), UNIQUE (access_code))""",
    'CREATE INDEX ix_quiz_bank_teacher_id ON quiz_bank (teacher_id)',
    """CREATE TABLE question (
        id INTEGER NOT NULL, title VARCHAR(200) NOT NULL, question_text TEXT NOT NULL,
        question_type VARCHAR(50) NOT NULL, question_data TEXT, points FLOAT, order_index INTEGER,
        category VARCHAR(100), quiz_bank_id INTEGER NOT NULL, created_at DATETIME,
        PRIMARY KEY (id), FOREIGN KEY(quiz_bank_id) REFERENCES quiz_bank (id))""",
    """CREATE TABLE submission (
        id INTEGER NOT NULL, student_name VARCHAR(100) NOT NULL, student_email VARCHAR(120),
        answers TEXT, score FLOAT, total_points FLOAT, is_practice BOOLEAN, session_question_ids TEXT,
        review_flag_question_ids TEXT, scoring_mode VARCHAR(20), scoring_total_points FLOAT,
        elapsed_seconds INTEGER, submitted_at DATETIME, quiz_bank_id INTEGER NOT NULL,
        result_token VARCHAR(64), PRIMARY KEY (id), FOREIGN KEY(quiz_bank_id) REFERENCES quiz_bank (id))""",
    'CREATE UNIQUE INDEX ix_submission_result_token ON submission (result_token)',
]

T1 = datetime(2026, 9, 1, 2, 0, 0)  # UTC


def _drop_everything():
    with app_module.db.engine.begin() as conn:
        conn.execute(text('PRAGMA foreign_keys=OFF'))
        for name in inspect(conn).get_table_names():
            conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))


@pytest.fixture
def old_db():
    """An old-schema database: Teacher 42 has banks A (2 Submissions, 20 min), B (none), C (1, untimed);
    Teacher 7 has bank D (1 Submission)."""
    app_module.app.config['TESTING'] = True
    app_module.app.config['SECRET_KEY'] = 'test-secret'
    with app_module.app.app_context():
        app_module.db.session.remove()
        app_module.db.engine.dispose()
        _drop_everything()
        with app_module.db.engine.begin() as conn:
            for ddl in OLD_SCHEMA:
                conn.execute(text(ddl))
            banks = [(1, 'A', 'OLDAAA', 1, 20, 42), (2, 'B', 'OLDBBB', 1, None, 42),
                     (3, 'C', 'OLDCCC', 0, None, 42), (4, 'D', 'OLDDDD', 1, 15, 7)]
            for bank_id, title, code, active, limit, teacher in banks:
                conn.execute(text(
                    "INSERT INTO quiz_bank (id, title, description, access_code, is_active, quiz_mode, "
                    "session_question_count, scoring_mode, scoring_total_points, time_limit_minutes, "
                    "created_at, teacher_id) VALUES (:id, :t, '', :c, :a, 'fixed', 10, 'explicit', 100, "
                    ":l, :at, :teacher)"),
                    dict(id=bank_id, t=title, c=code, a=active, l=limit, at=T1, teacher=teacher))
                conn.execute(text(
                    "INSERT INTO question (title, question_text, question_type, question_data, points, "
                    "order_index, quiz_bank_id) VALUES ('Q', 'What?', 'single_choice', "
                    "'{\"options\": [\"A\", \"B\"], \"correct_answer\": \"A\"}', 1, 0, :b)"), dict(b=bank_id))
            subs = [(1, 1, '小明', T1 + timedelta(minutes=5)), (2, 1, '小華', T1 + timedelta(minutes=40)),
                    (3, 3, '小明', T1 + timedelta(days=2)), (4, 4, '小美', T1 + timedelta(days=3))]
            for sub_id, bank_id, name, at in subs:
                conn.execute(text(
                    "INSERT INTO submission (id, student_name, answers, score, total_points, is_practice, "
                    "session_question_ids, submitted_at, quiz_bank_id, result_token, elapsed_seconds) "
                    "VALUES (:id, :n, '{}', 1, 1, 0, '[]', :at, :b, :tok, 60)"),
                    dict(id=sub_id, n=name, at=at, b=bank_id, tok=f'old-token-{sub_id}'))
        app_module.initialize_database()
    yield app_module.app.test_client()
    with app_module.app.app_context():
        app_module.db.session.remove()
        _drop_everything()
        app_module.db.engine.dispose()


def _sessions_by_bank():
    rows = {}
    for cs in app_module.ClassSession.query.all():
        for offer in cs.offers:
            rows[offer.quiz_bank_id] = (cs, offer)
    return rows


def test_each_teacher_with_old_submissions_gets_one_ended_course(old_db):
    with app_module.app.app_context():
        courses = app_module.Course.query.order_by(app_module.Course.teacher_id).all()
        assert [(c.teacher_id, c.name) for c in courses] == [(7, '改版前'), (42, '改版前')]
        assert all(c.ended_at is not None for c in courses)


def test_each_quiz_bank_with_submissions_gets_one_ended_class_session(old_db):
    with app_module.app.app_context():
        by_bank = _sessions_by_bank()
        assert sorted(by_bank) == [1, 3, 4]  # B had no Submission
        assert app_module.ClassSession.query.count() == 3
        a_session, a_offer = by_bank[1]
        assert a_session.name == '改版前的作答'
        assert a_session.course.name == '改版前' and a_session.course.teacher_id == 42
        assert a_session.teacher_id == 42
        assert (a_session.starts_at, a_session.ends_at) == (T1 + timedelta(minutes=5), T1 + timedelta(minutes=40))
        assert a_offer.time_limit_minutes == 20  # the Quiz Bank's old Time Limit
        assert by_bank[3][1].time_limit_minutes is None
        assert by_bank[4][0].course.teacher_id == 7
        assert by_bank[1][0].course_id == by_bank[3][0].course_id  # one Course per Teacher
        assert len({cs.code for cs, _ in by_bank.values()}) == 3
        assert not {cs.code for cs, _ in by_bank.values()} & {'OLDAAA', 'OLDCCC', 'OLDDDD'}
        now = datetime.utcnow()
        assert all(app_module.class_session_rules.status(cs, now) == 'done' for cs, _ in by_bank.values())


def test_every_old_submission_is_attached_to_its_quiz_bank_class_session(old_db):
    with app_module.app.app_context():
        by_bank = _sessions_by_bank()
        subs = app_module.Submission.query.order_by(app_module.Submission.id).all()
        assert len(subs) == 4
        for sub in subs:
            assert sub.class_session_id == by_bank[sub.quiz_bank_id][0].id
            assert sub.class_session.course.name == '改版前'


def test_old_columns_are_dropped_and_class_session_is_required(old_db):
    with app_module.app.app_context():
        inspector = inspect(app_module.db.engine)
        bank_cols = {c['name'] for c in inspector.get_columns('quiz_bank')}
        assert not bank_cols & {'access_code', 'is_active', 'time_limit_minutes'}
        assert {'title', 'teacher_id', 'folder_id'} <= bank_cols
        sub_cols = {c['name']: c for c in inspector.get_columns('submission')}
        assert sub_cols['class_session_id']['nullable'] is False
        # Rows survive the table rebuilds.
        assert app_module.QuizBank.query.count() == 4
        assert app_module.Question.query.count() == 4


def test_running_the_migration_again_changes_nothing(old_db):
    with app_module.app.app_context():
        app_module.initialize_database()
        assert app_module.Course.query.count() == 2
        assert app_module.ClassSession.query.count() == 3


def test_the_app_works_on_the_migrated_database(old_db):
    client = old_db
    assert client.get('/quiz/OLDAAA').status_code == 404
    assert client.get('/result/old-token-1').status_code == 200
    sign_in(client, 42)
    client.environ_base['HTTP_ORIGIN'] = OWN_ORIGIN
    assert client.get('/class-sessions?status=all').status_code == 200
    assert '改版前的作答' in client.get('/class-sessions?status=all').get_data(as_text=True)
    created = client.post('/create-quiz-bank', json={'title': '新題庫', 'description': ''})
    assert created.status_code == 200
    assert client.delete('/api/quiz-bank/1', json={'confirm': True}).status_code == 200
    with app_module.app.app_context():
        assert app_module.Submission.query.filter_by(quiz_bank_id=1).count() == 0
