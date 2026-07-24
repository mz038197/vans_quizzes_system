import pytest
from werkzeug.security import generate_password_hash

import app as app_module


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / 'test.db'
    app_module.app.config['TESTING'] = True
    app_module.app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app_module.app.config['SECRET_KEY'] = 'test-secret'

    with app_module.app.app_context():
        app_module.db.engine.dispose()
        app_module.db.create_all()
        app_module.ensure_schema_updates()

        teacher = app_module.User(
            username='teacher',
            email='teacher@example.com',
            password_hash=generate_password_hash('password'),
            is_teacher=True,
        )
        app_module.db.session.add(teacher)
        app_module.db.session.commit()

        quiz_bank = app_module.QuizBank(
            title='Timed Bank',
            description='',
            access_code='ABC123',
            teacher_id=teacher.id,
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
            'teacher_id': teacher.id,
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
    response = client.post(
        '/login',
        json={'username': 'teacher', 'password': 'password'},
    )
    assert response.status_code == 200
    return client
