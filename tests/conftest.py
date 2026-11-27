import os
import tempfile

import pytest

# Flask-SQLAlchemy binds its engine when `app` is imported, so the test database must be
# chosen before that import. Without this, tests ran on (and dropped) instance/quiz_platform.db.
_TEST_DB_DIR = tempfile.mkdtemp(prefix='vans-quizzes-tests-')
os.environ['QUIZZES_DEV_DATABASE_URL'] = 'sqlite:///' + os.path.join(_TEST_DB_DIR, 'test.db').replace('\\', '/')
os.environ.pop('ROUTER_URL', None)
os.environ['FLASK_ENV'] = 'development'

import app as app_module  # noqa: E402
import teacher_auth  # noqa: E402

TEACHER_ROUTER_ID = 42
OWN_ORIGIN = 'http://localhost'


@pytest.fixture
def client(tmp_path):
    app_module.app.config['TESTING'] = True
    app_module.app.config['SECRET_KEY'] = 'test-secret'

    with app_module.app.app_context():
        app_module.db.engine.dispose()
        app_module.db.create_all()
        app_module.ensure_schema_updates()

        quiz_bank = app_module.QuizBank(
            title='Timed Bank',
            description='',
            access_code='ABC123',
            teacher_id=TEACHER_ROUTER_ID,
            quiz_mode='fixed',
        )
        app_module.db.session.add(quiz_bank)
        app_module.db.session.commit()

        question = app_module.Question(
            title='Q1',
            question_text='What?',
            question_type='single_choice',
            question_data='{"options": ["A", "B"], "correct_answer": "A"}',
            points=1,
            order_index=0,
            quiz_bank_id=quiz_bank.id,
        )
        app_module.db.session.add(question)
        app_module.db.session.commit()

        ids = {
            'teacher_id': TEACHER_ROUTER_ID,
            'quiz_bank_id': quiz_bank.id,
            'access_code': quiz_bank.access_code,
            'question_id': question.id,
        }

    test_client = app_module.app.test_client()
    test_client._ids = ids  # type: ignore[attr-defined]
    yield test_client

    with app_module.app.app_context():
        app_module.db.session.remove()
        app_module.db.drop_all()
        app_module.db.engine.dispose()


@pytest.fixture
def auth_client(client):
    """A signed-in Teacher whose writes come from this site's own origin."""
    sign_in(client, TEACHER_ROUTER_ID)
    client.environ_base['HTTP_ORIGIN'] = OWN_ORIGIN
    return client


def sign_in(client, user_id, name='測試老師'):
    with app_module.app.test_request_context():
        value = teacher_auth.sign_teacher_cookie(teacher_auth.Teacher(user_id=user_id, display_name=name))
    client.set_cookie(teacher_auth.TEACHER_COOKIE, value)


# ---- Class Sessions (ticket 09, issue #11) ----

def utc8_local(utc_dt):
    """A naive UTC time as the 'YYYY-MM-DDTHH:MM:SS' wall clock in UTC+8 that the open-session dialog sends."""
    from datetime import timedelta
    return (utc_dt + timedelta(hours=8)).strftime('%Y-%m-%dT%H:%M:%S')


def make_class_session(ids, starts_in=-60, ends_in=3000, time_limit=None, course_ends_in=None,
                       course_ended=False, name='測試課堂', teacher_id=TEACHER_ROUTER_ID):
    """Insert a Course and a Class Session offering the fixture Quiz Bank; times are seconds from now (UTC).

    Returns the Class Session code. Use it for windows the API cannot make (an end in the past).
    """
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    with app_module.app.app_context():
        course = app_module.Course(
            teacher_id=teacher_id, name=f'{name} 的課程',
            ends_at=None if course_ends_in is None else now + timedelta(seconds=course_ends_in),
            ended_at=now - timedelta(minutes=5) if course_ended else None,  # past the hand-in grace
        )
        app_module.db.session.add(course)
        app_module.db.session.flush()
        class_session = app_module.ClassSession(
            teacher_id=teacher_id, course_id=course.id, name=name,
            code=app_module.new_class_session_code(),
            starts_at=now + timedelta(seconds=starts_in), ends_at=now + timedelta(seconds=ends_in),
        )
        app_module.db.session.add(class_session)
        app_module.db.session.flush()
        app_module.db.session.add(app_module.ClassSessionBank(
            class_session_id=class_session.id, quiz_bank_id=ids['quiz_bank_id'],
            position=0, time_limit_minutes=time_limit,
        ))
        app_module.db.session.commit()
        return class_session.code
