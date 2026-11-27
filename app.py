from flask import Flask, abort, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import base64
import binascii
import csv
import io
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from werkzeug.exceptions import NotFound
from urllib.parse import quote
import os
import sys
from md_quiz_parser import parse_md_quiz, parse_md_questions_append
from practice_utils import (
    build_take_order,
    draw_practice_questions,
    get_category_ratios,
    normalize_review_flag_ids,
    parse_review_flag_ids,
    questions_in_id_order,
    serialize_question,
    validate_category_ratios,
)
from time_display import format_wall_clock_utc8
from page_nav import register_page_nav
import teacher_stats
import class_session_rules
import grade_stats
import grade_sheets
from teacher_auth import (
    DEFAULT_SECRET_KEY,
    LOGIN_REQUIRED,
    LOGIN_REQUIRED_NOTICE,
    NON_TEACHER_HINT,
    LoginError,
    check_environment,
    configure_teacher_auth,
    current_teacher,
    login_url as teacher_login_url,
    teacher_required,
)

logger = logging.getLogger(__name__)

# 環境設置
# No default: a missing FLASK_ENV must not quietly become development (teacher_auth.check_environment).
ENVIRONMENT = check_environment(os.environ.get('FLASK_ENV'))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', DEFAULT_SECRET_KEY)
app.jinja_env.filters['utc8'] = format_wall_clock_utc8

def normalize_database_url(database_url):
    """Name the psycopg2 driver outright.

    render.com gives `postgres://`. SQLAlchemy 2.1 reads a bare `postgresql://` as psycopg 3,
    which requirements.txt does not install, so the app would not start.
    """
    for prefix in ('postgres://', 'postgresql://'):
        if database_url.startswith(prefix):
            return 'postgresql+psycopg2://' + database_url[len(prefix):]
    return database_url

# 根據環境選擇數據庫
if ENVIRONMENT == 'production':
    app.config['SQLALCHEMY_DATABASE_URI'] = normalize_database_url(os.environ.get('DATABASE_URL', ''))
else:  # development
    # Tests point this at a temporary database; Flask-SQLAlchemy binds the engine at import time.
    app.config['SQLALCHEMY_DATABASE_URI'] = normalize_database_url(
        os.environ.get('QUIZZES_DEV_DATABASE_URL', 'sqlite:///quiz_platform.db')
    )

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024

ALLOWED_QUESTION_IMAGE_MIMES = frozenset({
    'image/png', 'image/jpeg', 'image/gif', 'image/webp',
})
QUESTION_IMAGE_MAX_BYTES = 2 * 1024 * 1024
_DATA_URL_IMAGE_RE = re.compile(
    r'^data:(image/(?:png|jpeg|gif|webp));base64,([A-Za-z0-9+/=]+)$',
)

db = SQLAlchemy(app)
CORS(app)
configure_teacher_auth(app, ENVIRONMENT)
register_page_nav(app)

# 模板過濾器
@app.template_filter('from_json')
def from_json_filter(value):
    try:
        return json.loads(value) if value else {}
    except:
        return {}

# Question types in display order, with their names (templates get it as `question_type_names`).
QUESTION_TYPE_NAMES = {
    'single_choice': '單選題',
    'multiple_choice': '多選題',
    'fill_blank': '填空題',
    'dropdown': '下拉選單',
    'dropdown_fillblank': '下拉選單填空題',
    'parsons': '程式碼排序題',
}
app.jinja_env.globals['question_type_names'] = QUESTION_TYPE_NAMES

@app.template_global()
def quiz_mode_label(quiz_mode):
    """隨機練習 for a practice Quiz Bank, else 固定測驗."""
    return '隨機練習' if quiz_mode == 'practice' else '固定測驗'


@app.template_global()
def get_question_type_name(question_type):
    return QUESTION_TYPE_NAMES.get(question_type, question_type)

def new_result_token():
    """The secret part of a Result Link (ADR 0008)."""
    return secrets.token_urlsafe(24)

# 資料庫模型
class QuizBank(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    quiz_mode = db.Column(db.String(20), default='fixed')
    session_question_count = db.Column(db.Integer, default=10)
    category_ratios = db.Column(db.Text)
    scoring_mode = db.Column(db.String(20), default='explicit')  # explicit | average
    scoring_total_points = db.Column(db.Float, default=100)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    teacher_id = db.Column(db.Integer, nullable=False, index=True)  # router user id (ADR 0007)
    folder_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=True, index=True)  # ADR 0009; null = 未分類

    # 關聯
    questions = db.relationship('Question', backref='quiz_bank', lazy=True, cascade='all, delete-orphan')
    submissions = db.relationship('Submission', backref='quiz_bank', lazy=True, cascade='all, delete-orphan')

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(50), nullable=False)  # single_choice, multiple_choice, fill_blank, dropdown, parsons
    question_data = db.Column(db.Text)  # JSON格式儲存選項、正確答案等
    points = db.Column(db.Float, default=1)
    order_index = db.Column(db.Integer, default=0)
    category = db.Column(db.String(100))
    quiz_bank_id = db.Column(db.Integer, db.ForeignKey('quiz_bank.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(100), nullable=False)
    student_email = db.Column(db.String(120))
    answers = db.Column(db.Text)  # JSON格式儲存答案
    score = db.Column(db.Float, default=0)
    total_points = db.Column(db.Float, default=0)
    is_practice = db.Column(db.Boolean, default=False)
    session_question_ids = db.Column(db.Text)  # Take Order (question ids JSON)
    review_flag_question_ids = db.Column(db.Text)  # Review Flags at hand-in (question ids JSON)
    scoring_mode = db.Column(db.String(20))  # snapshot at submit time
    scoring_total_points = db.Column(db.Float)
    elapsed_seconds = db.Column(db.Integer)  # Elapsed Time for timed Takes
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    quiz_bank_id = db.Column(db.Integer, db.ForeignKey('quiz_bank.id'), nullable=False)
    result_token = db.Column(db.String(64), unique=True, index=True, default=new_result_token)  # Result Link (ADR 0008)
    # The Class Session this Take ran in (required; old Submissions moved to 「改版前的作答」, issue #16).
    class_session_id = db.Column(db.Integer, db.ForeignKey('class_session.id'), nullable=False, index=True)

# ---- Courses and Class Sessions (ADR 0010, ADR 0011). Time rules live in class_session_rules.py. ----

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    ends_at = db.Column(db.DateTime)  # UTC; 23:59 UTC+8 of the chosen day; null = no end date
    ended_at = db.Column(db.DateTime)  # UTC; set by 結束課程, cleared by reopen
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class_sessions = db.relationship('ClassSession', backref='course', lazy=True, cascade='all, delete-orphan')

class ClassSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(12), unique=True, nullable=False, index=True)
    starts_at = db.Column(db.DateTime, nullable=False)  # UTC
    ends_at = db.Column(db.DateTime, nullable=False)  # UTC
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    offers = db.relationship('ClassSessionBank', backref='class_session', lazy=True,
                             order_by='ClassSessionBank.position', cascade='all, delete-orphan')
    submissions = db.relationship('Submission', backref='class_session', lazy=True, cascade='all, delete')

class ClassSessionBank(db.Model):
    """One Quiz Bank offered by a Class Session, with its own optional Time Limit."""
    __table_args__ = (db.UniqueConstraint('class_session_id', 'quiz_bank_id'),)
    id = db.Column(db.Integer, primary_key=True)
    class_session_id = db.Column(db.Integer, db.ForeignKey('class_session.id'), nullable=False, index=True)
    quiz_bank_id = db.Column(db.Integer, db.ForeignKey('quiz_bank.id'), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    time_limit_minutes = db.Column(db.Integer)  # null = no Time Limit

    quiz_bank = db.relationship('QuizBank', backref=db.backref('offers', lazy=True, cascade='all, delete-orphan'))

NOT_FOUND_TEXT = '找不到資料'


def is_own(record):
    """The one ownership rule: a Teacher manages only what they own; an admin is no exception (ADR 0007).

    `record` is a Quiz Bank, Folder, Course or Class Session (its teacher_id), or a Question or
    Submission (its Quiz Bank's teacher_id). None is nobody's.
    """
    if record is None:
        return False
    owner = record.teacher_id if hasattr(record, 'teacher_id') else record.quiz_bank.teacher_id
    return owner == current_teacher().user_id


def owned_or_404(model, record_id, message=NOT_FOUND_TEXT):
    """The record of this Teacher, else 404, for pages and APIs alike: "not yours" looks like
    "not there" (no 403, no redirect). API paths get JSON {error} (see json_not_found)."""
    try:
        record = db.session.get(model, int(record_id))
    except (TypeError, ValueError):
        record = None
    if not is_own(record):
        abort(404, description=message)
    return record


def owned_or_none(model, record_id):
    """Like owned_or_404 for an id inside a request body: the record, or None when it is missing or not yours."""
    try:
        record = db.session.get(model, int(record_id))
    except (TypeError, ValueError):
        return None
    return record if is_own(record) else None


@app.errorhandler(404)
def json_not_found(error):
    """API callers get JSON; pages keep the normal 404 page."""
    if request.path.startswith('/api/'):
        description = error.description if error.description != NotFound.description else NOT_FOUND_TEXT
        return jsonify({'error': description}), 404
    return error

LATE_HAND_IN_ERROR = '課堂已結束，這份作答沒有被收下'

@app.template_global()
def class_session_window(class_session):
    """The window as shown (UTC+8), e.g. '11/27 10:00–10:50'."""
    return class_session_rules.window_text(class_session.starts_at, class_session.ends_at)

def new_class_session_code():
    """An unguessable 6-character Class Session code that no Class Session uses."""
    while True:
        code = class_session_rules.random_code()
        if not ClassSession.query.filter_by(code=code).first():
            return code

def parse_points(value, default=1.0):
    """Validate and coerce points to a positive float. Returns (points, error_or_None)."""
    if value is None or value == '':
        value = default
    try:
        points = float(value)
    except (TypeError, ValueError):
        return None, 'points 必須是數字'
    if points <= 0:
        return None, 'points 必須大於 0'
    return points, None


def ensure_schema_updates():
    """為既有資料庫補上新欄位（SQLite / PostgreSQL 簡易 migration）。"""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    dialect_name = db.engine.dialect.name
    is_postgres = dialect_name == 'postgresql'
    is_sqlite = dialect_name == 'sqlite'

    def column_names(table_name):
        return {column['name'] for column in inspector.get_columns(table_name)}

    def column_type_name(table_name, column_name):
        for column in inspector.get_columns(table_name):
            if column['name'] == column_name:
                return str(column['type']).upper()
        return ''

    def needs_float_migration(table_name, column_name):
        type_name = column_type_name(table_name, column_name)
        return type_name and 'INT' in type_name and 'POINT' not in type_name

    def sqlite_type_sql(column):
        type_name = str(column['type']).upper()
        if 'INT' in type_name and 'POINT' not in type_name:
            return 'INTEGER'
        if any(token in type_name for token in ('REAL', 'FLOAT', 'DOUBLE', 'NUMERIC', 'DECIMAL')):
            return 'REAL'
        if 'BOOL' in type_name:
            return 'BOOLEAN'
        if 'DATE' in type_name or 'TIME' in type_name:
            return 'DATETIME'
        if 'CHAR' in type_name or 'TEXT' in type_name or 'CLOB' in type_name:
            return 'TEXT'
        return 'TEXT'

    # Model-defined FKs used when inspector finds none (e.g. after a prior rebuild dropped them).
    expected_sqlite_foreign_keys = {
        'question': [{
            'constrained_columns': ['quiz_bank_id'],
            'referred_table': 'quiz_bank',
            'referred_columns': ['id'],
        }],
        'submission': [{
            'constrained_columns': ['quiz_bank_id'],
            'referred_table': 'quiz_bank',
            'referred_columns': ['id'],
        }],
    }

    def sqlite_foreign_key_defs(table_name):
        fks = inspector.get_foreign_keys(table_name)
        if not fks:
            fks = expected_sqlite_foreign_keys.get(table_name, [])
        defs = []
        for fk in fks:
            constrained = ', '.join(fk['constrained_columns'])
            referred_table = fk['referred_table']
            referred = ', '.join(fk['referred_columns'])
            fk_sql = f'FOREIGN KEY ({constrained}) REFERENCES {referred_table} ({referred})'
            options = fk.get('options') or {}
            if options.get('ondelete'):
                fk_sql += f' ON DELETE {options["ondelete"]}'
            if options.get('onupdate'):
                fk_sql += f' ON UPDATE {options["onupdate"]}'
            defs.append(fk_sql)
        return defs

    def missing_expected_foreign_keys(table_name):
        expected = expected_sqlite_foreign_keys.get(table_name, [])
        if not expected:
            return False
        existing = {
            (tuple(fk['constrained_columns']), fk['referred_table'], tuple(fk['referred_columns']))
            for fk in inspector.get_foreign_keys(table_name)
        }
        for fk in expected:
            key = (
                tuple(fk['constrained_columns']),
                fk['referred_table'],
                tuple(fk['referred_columns']),
            )
            if key not in existing:
                return True
        return False

    def rebuild_sqlite_table(table_name, type_overrides=None):
        """Rebuild a SQLite table, optionally overriding column types, preserving FKs."""
        type_overrides = type_overrides or {}
        columns = inspector.get_columns(table_name)
        col_names = [column['name'] for column in columns]
        col_defs = []
        for column in columns:
            name = column['name']
            sql_type = type_overrides.get(name) or sqlite_type_sql(column)
            pieces = [name, sql_type]
            if column.get('primary_key'):
                pieces.append('PRIMARY KEY')
            elif not column.get('nullable', True):
                pieces.append('NOT NULL')
            col_defs.append(' '.join(pieces))

        col_defs.extend(sqlite_foreign_key_defs(table_name))

        tmp_table = f'{table_name}__float_mig'
        cols_csv = ', '.join(col_names)
        db.session.execute(text('PRAGMA foreign_keys=OFF'))
        db.session.execute(text(f'DROP TABLE IF EXISTS {tmp_table}'))
        db.session.execute(text(f'CREATE TABLE {tmp_table} ({", ".join(col_defs)})'))
        db.session.execute(text(
            f'INSERT INTO {tmp_table} ({cols_csv}) SELECT {cols_csv} FROM {table_name}'
        ))
        db.session.execute(text(f'DROP TABLE {table_name}'))
        db.session.execute(text(f'ALTER TABLE {tmp_table} RENAME TO {table_name}'))
        db.session.execute(text('PRAGMA foreign_keys=ON'))
        db.session.commit()
        inspector.clear_cache()

    def migrate_sqlite_column_to_float(table_name, column_name):
        """Rebuild a SQLite table so an INTEGER column becomes REAL."""
        rebuild_sqlite_table(table_name, {column_name: 'REAL'})

    def run_migration(description, action):
        """Run a migration action; log and roll back on failure (e.g. concurrent DDL races)."""
        try:
            action()
        except Exception:
            db.session.rollback()
            logger.exception('Schema migration failed: %s', description)

    def apply_statement(statement):
        """Run one DDL statement; ignore races where another instance already applied it."""
        def _run():
            db.session.execute(text(statement))
            db.session.commit()

        run_migration(statement, _run)

    statements = []
    if 'quiz_bank' in table_names:
        cols = column_names('quiz_bank')
        if 'quiz_mode' not in cols:
            statements.append("ALTER TABLE quiz_bank ADD COLUMN quiz_mode VARCHAR(20) DEFAULT 'fixed'")
        if 'session_question_count' not in cols:
            statements.append('ALTER TABLE quiz_bank ADD COLUMN session_question_count INTEGER DEFAULT 10')
        if 'category_ratios' not in cols:
            statements.append('ALTER TABLE quiz_bank ADD COLUMN category_ratios TEXT')
        if 'scoring_mode' not in cols:
            statements.append("ALTER TABLE quiz_bank ADD COLUMN scoring_mode VARCHAR(20) DEFAULT 'explicit'")
        if 'scoring_total_points' not in cols:
            statements.append('ALTER TABLE quiz_bank ADD COLUMN scoring_total_points REAL DEFAULT 100')
        if 'folder_id' not in cols:
            statements.append('ALTER TABLE quiz_bank ADD COLUMN folder_id INTEGER REFERENCES folder(id)')

    if 'question' in table_names:
        cols = column_names('question')
        if 'category' not in cols:
            statements.append('ALTER TABLE question ADD COLUMN category VARCHAR(100)')
        if 'points' in cols and needs_float_migration('question', 'points'):
            if is_postgres:
                statements.append('ALTER TABLE question ALTER COLUMN points TYPE DOUBLE PRECISION')
            elif is_sqlite:
                run_migration(
                    'question.points INTEGER -> REAL',
                    lambda: migrate_sqlite_column_to_float('question', 'points'),
                )

    if 'submission' in table_names:
        cols = column_names('submission')
        bool_default = 'FALSE' if is_postgres else '0'
        if 'is_practice' not in cols:
            statements.append(f'ALTER TABLE submission ADD COLUMN is_practice BOOLEAN DEFAULT {bool_default}')
        if 'session_question_ids' not in cols:
            statements.append('ALTER TABLE submission ADD COLUMN session_question_ids TEXT')
        if 'scoring_mode' not in cols:
            statements.append('ALTER TABLE submission ADD COLUMN scoring_mode VARCHAR(20)')
        if 'scoring_total_points' not in cols:
            statements.append('ALTER TABLE submission ADD COLUMN scoring_total_points REAL')
        if 'elapsed_seconds' not in cols:
            statements.append('ALTER TABLE submission ADD COLUMN elapsed_seconds INTEGER')
        if 'review_flag_question_ids' not in cols:
            statements.append('ALTER TABLE submission ADD COLUMN review_flag_question_ids TEXT')
        if 'total_points' in cols and needs_float_migration('submission', 'total_points'):
            if is_postgres:
                statements.append('ALTER TABLE submission ALTER COLUMN total_points TYPE DOUBLE PRECISION')
            elif is_sqlite:
                run_migration(
                    'submission.total_points INTEGER -> REAL',
                    lambda: migrate_sqlite_column_to_float('submission', 'total_points'),
                )

    # Restore FKs dropped by earlier SQLite table rebuilds that omitted them.
    if is_sqlite:
        for table_name in ('question', 'submission'):
            if table_name in table_names and missing_expected_foreign_keys(table_name):
                run_migration(
                    f'{table_name} restore foreign keys',
                    lambda t=table_name: rebuild_sqlite_table(t),
                )

    for statement in statements:
        apply_statement(statement)

    # The model declares this index, but old databases got folder_id through ALTER TABLE without it.
    if 'quiz_bank' in table_names:
        apply_statement('CREATE INDEX IF NOT EXISTS ix_quiz_bank_folder_id ON quiz_bank (folder_id)')


def get_bank_scoring(quiz_bank):
    mode = (getattr(quiz_bank, 'scoring_mode', None) or 'explicit').strip().lower()
    if mode not in ('explicit', 'average'):
        mode = 'explicit'
    raw_total = getattr(quiz_bank, 'scoring_total_points', None)
    try:
        total = float(raw_total) if raw_total is not None else 100.0
    except (TypeError, ValueError):
        total = 100.0
    if total <= 0:
        total = 100.0
    return mode, total


def effective_points_map(questions, scoring_mode='explicit', total_points=100):
    """Return {question_id: effective_points} for this attempt's question list."""
    questions = list(questions)
    if not questions:
        return {}

    mode = (scoring_mode or 'explicit').strip().lower()
    if mode != 'average':
        return {q.id: float(q.points or 0) for q in questions}

    try:
        total = float(total_points)
    except (TypeError, ValueError):
        total = 100.0
    if total <= 0:
        total = 100.0

    n = len(questions)
    per = total / n
    points_map = {}
    allocated = 0.0
    for index, question in enumerate(questions):
        if index == n - 1:
            points_map[question.id] = round(total - allocated, 4)
        else:
            value = round(per, 4)
            points_map[question.id] = value
            allocated += value
    return points_map


def build_questions_data(questions, points_map=None):
    result = []
    for question in questions:
        data = serialize_question(question)
        if points_map is not None and question.id in points_map:
            data['points'] = points_map[question.id]
        result.append(data)
    return result

def _decode_question_image_payload(image_payload):
    """Return normalized image dict or None if invalid."""
    if not isinstance(image_payload, dict):
        return None

    data_url = str(image_payload.get('data_url', '') or '').strip()
    if not data_url:
        return None

    match = _DATA_URL_IMAGE_RE.match(data_url)
    if not match:
        return None

    mime_type = match.group(1)
    if mime_type not in ALLOWED_QUESTION_IMAGE_MIMES:
        return None

    try:
        raw_bytes = base64.b64decode(match.group(2), validate=True)
    except (ValueError, binascii.Error):
        return None

    if len(raw_bytes) > QUESTION_IMAGE_MAX_BYTES:
        return None

    filename = str(image_payload.get('filename', '') or '').strip()
    normalized = {
        'data_url': data_url,
        'mime_type': mime_type,
    }
    if filename:
        normalized['filename'] = filename
    return normalized


def normalize_question_image(data):
    """Keep a valid question image or remove the key."""
    if 'image' not in data:
        return data

    normalized_image = _decode_question_image_payload(data.get('image'))
    if normalized_image:
        data['image'] = normalized_image
    else:
        data.pop('image', None)
    return data


def normalize_question_data(raw_data):
    """Drop empty explanation/image so cleared edits do not leave stale values."""
    data = dict(raw_data or {})
    explanation = str(data.get('explanation', '') or '').strip()
    if explanation:
        data['explanation'] = explanation
    else:
        data.pop('explanation', None)
    normalize_question_image(data)
    return data


def validate_question_data_payload(raw_data):
    """Return (normalized_data, error_message)."""
    payload = dict(raw_data or {})
    had_image = 'image' in payload
    normalized = normalize_question_data(payload)
    if had_image and 'image' not in normalized:
        return None, '圖片格式不支援或超過 2MB'
    return normalized, None

def get_practice_session_key(take_key):
    return f'practice_session_{take_key}'


def get_take_session_key(take_key):
    return f'take_session_{take_key}'


def get_or_create_fixed_take_order(take_key, bank_question_ids):
    """Freeze Take Order for a fixed Quiz Bank Take in the Flask session."""
    key = get_take_session_key(take_key)
    bank_ids = list(bank_question_ids)
    data = session.get(key) or {}
    stored = data.get('question_ids') or []
    if stored and set(stored) == set(bank_ids) and len(stored) == len(bank_ids):
        return list(stored)
    ordered = build_take_order(bank_ids)
    session[key] = {'question_ids': ordered}
    return ordered


def load_fixed_take_questions(take_key, quiz_bank_id):
    bank_questions = Question.query.filter_by(quiz_bank_id=quiz_bank_id).order_by(Question.order_index).all()
    bank_ids = [q.id for q in bank_questions]
    take_order = get_or_create_fixed_take_order(take_key, bank_ids)
    return questions_in_id_order(bank_questions, take_order), take_order


def resolve_fixed_take_order_for_submit(take_key, bank_question_ids):
    """Use the frozen Take Order from session; never invent a new permutation at hand-in."""
    bank_ids = list(bank_question_ids)
    data = session.get(get_take_session_key(take_key)) or {}
    stored = data.get('question_ids') or []
    if stored and set(stored) == set(bank_ids) and len(stored) == len(bank_ids):
        return list(stored)
    return bank_ids

def create_quiz_bank_from_data(teacher_id, bank_data):
    quiz_bank = QuizBank(
        title=bank_data['title'],
        description=bank_data.get('description', ''),
        teacher_id=teacher_id,
        quiz_mode=bank_data.get('quiz_mode', 'fixed'),
        session_question_count=bank_data.get('session_question_count') or 10,
        category_ratios=json.dumps(bank_data.get('category_ratios') or {}) if bank_data.get('category_ratios') else None,
    )
    db.session.add(quiz_bank)
    db.session.flush()
    return quiz_bank

def create_questions_for_bank(quiz_bank_id, questions_data, start_order=1):
    for offset, item in enumerate(questions_data):
        question = Question(
            title=item['title'],
            question_text=item['question_text'],
            question_type=item['question_type'],
            question_data=json.dumps(normalize_question_data(item.get('question_data', {}))),
            points=item.get('points', 1),
            order_index=start_order + offset,
            category=item.get('category'),
            quiz_bank_id=quiz_bank_id,
        )
        db.session.add(question)

def grade_question(question, user_answer, points=None):
    question_data = json.loads(question.question_data) if question.question_data else {}
    if points is None:
        points = question.points

    if question.question_type in ['single_choice', 'dropdown']:
        correct_answer = question_data.get('correct_answer')
        is_correct = False
        if user_answer == correct_answer:
            is_correct = True
        elif str(user_answer) == str(correct_answer):
            is_correct = True
        elif str(user_answer).strip() == str(correct_answer).strip():
            is_correct = True
        else:
            import re
            user_normalized = str(user_answer).replace('\r\n', '\n').replace('\r', '\n').strip() if user_answer else ''
            correct_normalized = str(correct_answer).replace('\r\n', '\n').replace('\r', '\n').strip() if correct_answer else ''
            if user_normalized == correct_normalized:
                is_correct = True
            elif re.sub(r'\s+', '', str(user_answer)) == re.sub(r'\s+', '', str(correct_answer)):
                is_correct = True
        return points if is_correct else 0

    if question.question_type == 'dropdown_fillblank':
        blanks_data = question_data.get('blanks', [])
        user_answers = user_answer if isinstance(user_answer, dict) else {}
        for i, blank in enumerate(blanks_data):
            blank_id = f'blank_{i}'
            if user_answers.get(blank_id) != blank.get('correct_answer'):
                return 0
        return points if len(user_answers) == len(blanks_data) else 0

    if question.question_type == 'multiple_choice':
        correct_answers = set(question_data.get('correct_answers', []))
        user_answers = set(user_answer if isinstance(user_answer, list) else [])
        return points if user_answers == correct_answers else 0

    if question.question_type == 'fill_blank':
        correct_answer = question_data.get('correct_answer', '').lower().strip()
        user_answer_clean = (user_answer or '').lower().strip()
        return points if user_answer_clean == correct_answer else 0

    if question.question_type == 'parsons':
        if 'slot_answers' in question_data and isinstance(user_answer, dict) and 'slot_answers' in user_answer:
            correct_slot_answers = question_data.get('slot_answers', {})
            user_slot_answers = user_answer.get('slot_answers', {})
            fixed_blocks = question_data.get('fixed_blocks', {})
            correct_slot_answers_filtered = {
                slot: label for slot, label in correct_slot_answers.items()
                if slot not in fixed_blocks
            }
            for slot_num, correct_label in correct_slot_answers_filtered.items():
                if user_slot_answers.get(str(slot_num)) != correct_label:
                    return 0
            return points if len(user_slot_answers) == len(correct_slot_answers_filtered) else 0

        if 'correct_order' in question_data:
            correct_order = question_data.get('correct_order', [])
            user_order = []
            if isinstance(user_answer, dict) and 'order' in user_answer:
                user_order = user_answer['order'] if isinstance(user_answer['order'], list) else []
            elif isinstance(user_answer, dict) and 'slot_answers' in user_answer:
                slot_answers = user_answer['slot_answers']
                sorted_slots = sorted([int(k) for k in slot_answers.keys()])
                user_order = [slot_answers[str(slot)] for slot in sorted_slots]
            elif isinstance(user_answer, dict):
                for i in range(1, len(correct_order) + 1):
                    if str(i) in user_answer:
                        user_order.append(user_answer[str(i)])
                    elif i in user_answer:
                        user_order.append(user_answer[i])
            elif isinstance(user_answer, list):
                user_order = user_answer
            if len(user_order) == len(correct_order) and all(a == b for a, b in zip(user_order, correct_order)):
                return points

    return 0

# 路由定義
@app.route('/')
def index():
    error_code = request.args.get('error')
    return render_template(
        'index.html',
        login_error=LoginError.notice_for(error_code),
        login_error_hint=NON_TEACHER_HINT if error_code == LoginError.LOGIN_FAILED.value else None,
        login_required=LOGIN_REQUIRED_NOTICE if request.args.get('notice') == LOGIN_REQUIRED else None,
        login_url=teacher_login_url(request.args.get('next')),
    )

@app.route('/teacher-dashboard')
@teacher_required
def teacher_dashboard():
    teacher_id = current_teacher().user_id
    now = datetime.utcnow()
    sessions = teacher_class_session_overview(teacher_id, now)
    banks = teacher_bank_overview(teacher_id, now, sessions)
    since = now - 2 * teacher_stats.WEEK
    hand_ins = (db.session.query(Submission.student_name, Submission.submitted_at)
                .join(QuizBank).filter(QuizBank.teacher_id == teacher_id,
                                       Submission.submitted_at >= since).all())
    numbers = teacher_stats.week_numbers(hand_ins, now)
    numbers['week_delta_text'] = teacher_stats.delta_text(numbers['week_delta'])
    shown = [row for row in sessions if row['status'] != class_session_rules.DONE]
    numbers['live_sessions'] = sum(1 for row in shown if row['status'] == class_session_rules.LIVE)
    numbers['soon_sessions'] = len(shown) - numbers['live_sessions']
    numbers['attention'] = sum(1 for b in banks if b['attention'])
    recent = (db.session.query(Submission, QuizBank.title)
              .join(QuizBank).filter(QuizBank.teacher_id == teacher_id)
              .order_by(Submission.submitted_at.desc()).limit(8).all())
    recent = [{
        'submission': s, 'bank_title': title,
        'percent': teacher_stats.submission_percent(s.score, s.total_points),
    } for s, title in recent]
    return render_template('teacher_dashboard.html', banks=banks, numbers=numbers, recent=recent,
                           sessions=shown, cs_dialog=class_session_dialog_data(teacher_id))


@app.route('/quiz-banks')
@teacher_required
def quiz_banks():
    teacher_id = current_teacher().user_id
    now = datetime.utcnow()
    sessions = teacher_class_session_overview(teacher_id, now)
    banks = teacher_bank_overview(teacher_id, now, sessions)
    folders = teacher_folders(teacher_id)
    folder = None
    if request.args.get('folder'):
        folder = Folder.query.get_or_404(request.args.get('folder', type=int) or 0)
        if not is_own(folder):
            return redirect(url_for('quiz_banks'))
    attention_count = sum(1 for b in banks if b['attention'])
    attention_only = request.args.get('filter') == 'attention'
    query = (request.args.get('q') or '').strip()
    if query:
        shown = [b for b in banks if bank_matches(b['bank'], query)]
    elif attention_only:
        shown = [b for b in banks if b['attention']]
    else:
        here = folder.id if folder else None
        shown = [b for b in banks if b['bank'].folder_id == here]
    cards = []
    for f in folders:
        inside = [b for b in banks if b['bank'].folder_id == f.id]
        inside_ids = {b['bank'].id for b in inside}
        n_live = sum(1 for row in sessions if row['status'] == class_session_rules.LIVE
                     and any(o.quiz_bank_id in inside_ids for o in row['session'].offers))
        cards.append({'folder': f, 'n_banks': len(inside), 'n_live': n_live,
                      'n_attention': sum(1 for b in inside if b['attention'])})
    return render_template('quiz_banks.html', banks=shown, total=len(banks),
                           attention_count=attention_count, attention_only=attention_only, query=query,
                           folder=folder, folder_cards=cards, folder_colors=FOLDER_COLORS,
                           folders_json=[folder_json(f) for f in folders],
                           cs_dialog=class_session_dialog_data(teacher_id, folder.id if folder else None))


def bank_matches(bank, query):
    """True when the search text is in the Quiz Bank title or description, ignoring case."""
    needle = query.casefold()
    return needle in (bank.title or '').casefold() or needle in (bank.description or '').casefold()


def teacher_class_session_overview(teacher_id, now=None):
    """Every Class Session of the Teacher with its status, Submission count and distinct trimmed names.

    Sorted by class_session_rules.list_order (live, upcoming by start, ended by latest end).
    An ended Course makes its Class Sessions DONE (class_session_rules.status).
    """
    now = now or datetime.utcnow()
    class_sessions = ClassSession.query.filter_by(teacher_id=teacher_id).all()
    names = {}
    for session_id, name in (db.session.query(Submission.class_session_id, Submission.student_name)
                             .join(ClassSession).filter(ClassSession.teacher_id == teacher_id).all()):
        names.setdefault(session_id, []).append((name or '').strip())
    rows = []
    for class_session in class_sessions:
        status = class_session_rules.status(class_session, now)
        handed = names.get(class_session.id, [])
        row = {'session': class_session, 'status': status, 'n_subs': len(handed),
               'n_students': len(set(handed)), 'progress': None, 'when_text': None}
        if status == class_session_rules.LIVE:
            end = class_session_rules.effective_end(class_session)
            span = (end - class_session.starts_at).total_seconds() or 1
            done = (now - class_session.starts_at).total_seconds() / span * 100
            row['progress'] = max(0, min(100, round(done)))
            row['when_text'] = f'剩 {teacher_stats.duration_text(end - now)}'
        elif status == class_session_rules.SOON:
            row['when_text'] = f'{teacher_stats.duration_text(class_session.starts_at - now)}後'
        rows.append(row)
    return sorted(rows, key=lambda r: class_session_rules.list_order(r['session'], r['status']))


def teacher_bank_overview(teacher_id, now=None, sessions=None):
    """The Teacher's Quiz Banks, newest first, with question count, Submission count, average,
    Class Session status (session_kind, session_text) and 需要注意.

    `sessions` is teacher_class_session_overview(...) when the caller already has it.
    """
    now = now or datetime.utcnow()
    if sessions is None:
        sessions = teacher_class_session_overview(teacher_id, now)
    sessions_of = {}
    for row in sessions:
        for offer in row['session'].offers:
            sessions_of.setdefault(offer.quiz_bank_id, []).append(row)
    banks = (QuizBank.query.filter_by(teacher_id=teacher_id)
             .order_by(QuizBank.created_at.desc(), QuizBank.id.desc()).all())
    question_counts = dict(
        db.session.query(Question.quiz_bank_id, db.func.count(Question.id))
        .join(QuizBank).filter(QuizBank.teacher_id == teacher_id)
        .group_by(Question.quiz_bank_id).all()
    )
    scores = {}
    for bank_id, score, total in (db.session.query(Submission.quiz_bank_id, Submission.score, Submission.total_points)
                                  .join(QuizBank).filter(QuizBank.teacher_id == teacher_id).all()):
        scores.setdefault(bank_id, []).append((score, total))
    folder_by_id = {f.id: f for f in teacher_folders(teacher_id)}
    overview = []
    for bank in banks:
        average = teacher_stats.average_percent(scores.get(bank.id, []))
        own = sessions_of.get(bank.id, [])
        session_kind, session_text = teacher_stats.bank_session_status(
            (r['status'], r['session'].starts_at) for r in own)
        attention = teacher_stats.attention_reason(
            average, [(r['session'].name, r['status'], r['session'].starts_at, r['n_subs']) for r in own], now)
        overview.append({
            'bank': bank,
            'mode': quiz_mode_label(bank.quiz_mode),
            'n_questions': question_counts.get(bank.id, 0),
            'n_subs': len(scores.get(bank.id, [])),
            'average': average,
            'average_text': None if average is None else teacher_stats.percent_text(average),
            'attention': attention,
            'session_kind': session_kind,
            'session_text': session_text,
            'folder': folder_by_id.get(bank.folder_id),
        })
    return overview


# --- Folders (ADR 0009) -------------------------------------------------------

FOLDER_COLORS = ('blue', 'green', 'purple', 'amber', 'pink', 'cyan')


class Folder(db.Model):
    """A teacher-owned, named place for Quiz Banks. One level only; a Quiz Bank is in at most one Folder."""
    __table_args__ = (db.UniqueConstraint('teacher_id', 'name', name='uq_folder_teacher_name'),)
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(20), nullable=False, default='blue')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def teacher_folders(teacher_id):
    return Folder.query.filter_by(teacher_id=teacher_id).order_by(Folder.created_at, Folder.id).all()


def folder_json(folder):
    return {'id': folder.id, 'name': folder.name, 'color': folder.color}


def read_folder_fields(payload, teacher_id, folder_id=None):
    """Check a Folder name and colour. Returns (name, color, error)."""
    name = str(payload.get('name') or '').strip()
    color = payload.get('color') or 'blue'
    if not name:
        return None, None, '請輸入資料夾名稱'
    if len(name) > 100:
        return None, None, '資料夾名稱最多 100 個字'
    if color not in FOLDER_COLORS:
        return None, None, '請選一個資料夾顏色'
    same = Folder.query.filter_by(teacher_id=teacher_id, name=name).first()
    if same and same.id != folder_id:
        return None, None, f'已經有名稱是「{name}」的資料夾'
    return name, color, None


def owned_folder_or_error(folder_id):
    """(folder, None) for a Folder of this Teacher; (None, error response) if not. No id means 未分類."""
    if folder_id is None or folder_id == '':
        return None, None
    folder = owned_or_none(Folder, folder_id)
    if folder is None:
        return None, (jsonify({'error': '找不到資料夾'}), 404)
    return folder, None


@app.route('/api/folders', methods=['POST'])
@teacher_required
def create_folder():
    teacher_id = current_teacher().user_id
    name, color, error = read_folder_fields(request.get_json(silent=True) or {}, teacher_id)
    if error:
        return jsonify({'error': error}), 400
    folder = Folder(teacher_id=teacher_id, name=name, color=color)
    db.session.add(folder)
    db.session.commit()
    return jsonify({'message': '資料夾已建立', 'folder': folder_json(folder)}), 201


@app.route('/api/folders/<int:folder_id>', methods=['PUT', 'DELETE'])
@teacher_required
def manage_folder(folder_id):
    folder = owned_or_404(Folder, folder_id, '找不到資料夾')
    if request.method == 'DELETE':
        QuizBank.query.filter_by(folder_id=folder.id).update({'folder_id': None})
        db.session.delete(folder)
        db.session.commit()
        return jsonify({'message': '資料夾已刪除，裡面的題庫已移回未分類'})
    name, color, error = read_folder_fields(request.get_json(silent=True) or {}, folder.teacher_id, folder.id)
    if error:
        return jsonify({'error': error}), 400
    folder.name, folder.color = name, color
    db.session.commit()
    return jsonify({'message': '資料夾已更新', 'folder': folder_json(folder)})


@app.route('/api/quiz-banks/move', methods=['POST'])
@teacher_required
def move_quiz_banks():
    """Move Quiz Banks into one Folder, or to 未分類 with a null folder_id. All or nothing."""
    payload = request.get_json(silent=True) or {}
    ids = payload.get('quiz_bank_ids')
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
        return jsonify({'error': '請選擇要移動的題庫'}), 400
    folder, refused = owned_folder_or_error(payload.get('folder_id'))
    if refused:
        return refused
    banks = QuizBank.query.filter(QuizBank.id.in_(set(ids))).all()
    if len(banks) != len(set(ids)) or not all(is_own(b) for b in banks):
        return jsonify({'error': '找不到題庫'}), 404
    previous = [{'id': bank.id, 'folder_id': bank.folder_id} for bank in banks]
    for bank in banks:
        bank.folder_id = folder.id if folder else None
    db.session.commit()
    where = f'「{folder.name}」' if folder else '未分類'
    return jsonify({'message': f'已移動 {len(banks)} 個題庫到{where}', 'moved': len(banks),
                    'folder': folder_json(folder) if folder else None, 'previous': previous})

@app.route('/create-quiz-bank', methods=['GET', 'POST'])
@teacher_required
def create_quiz_bank():
    if request.method == 'POST':
        data = request.get_json()
        title = data.get('title')
        description = data.get('description', '')
        folder, refused = owned_folder_or_error(data.get('folder_id'))
        if refused:
            return refused

        quiz_bank = QuizBank(
            title=title,
            description=description,
            teacher_id=current_teacher().user_id,
            folder_id=folder.id if folder else None,
        )
        db.session.add(quiz_bank)
        db.session.commit()
        
        return jsonify({
            'message': '題庫建立成功',
            'quiz_bank_id': quiz_bank.id,
        })
    
    tab = request.args.get('tab')
    if tab not in ('manual', 'import'):
        tab = 'manual'
    folder = db.session.get(Folder, request.args.get('folder', type=int) or 0)
    if folder is not None and not is_own(folder):
        folder = None
    return render_template('create_quiz_bank.html', tab=tab, folder=folder)

@app.route('/quiz-bank/<int:quiz_bank_id>')
@teacher_required
def manage_quiz_bank(quiz_bank_id):
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)

    questions = Question.query.filter_by(quiz_bank_id=quiz_bank_id).order_by(Question.order_index).all()
    category_stats = {}
    for question in questions:
        category = (question.category or '').strip() or '未分類'
        category_stats[category] = category_stats.get(category, 0) + 1

    type_counts = []
    for question_type, name in QUESTION_TYPE_NAMES.items():
        count = sum(1 for question in questions if question.question_type == question_type)
        if count:
            type_counts.append((question_type, name, count))

    scoring_mode, scoring_total = get_bank_scoring(quiz_bank)
    if scoring_mode != 'average':
        scoring_total = sum(question.points or 0 for question in questions)

    tab = request.args.get('tab')
    if tab not in MANAGE_TABS:
        tab = MANAGE_TABS[0]

    return render_template(
        'manage_quiz_bank.html',
        quiz_bank=quiz_bank,
        questions=questions,
        category_stats=category_stats,
        category_ratios=get_category_ratios(quiz_bank),
        type_counts=type_counts,
        scoring_mode=scoring_mode,
        scoring_total=scoring_total,
        tab=tab,
        class_session_rows=quiz_bank_class_sessions(quiz_bank),
        cs_dialog=class_session_dialog_data(current_teacher().user_id, current_folder_id=quiz_bank.folder_id),
    )

# Tabs of the Quiz Bank manage page, in order. The first one opens by default.
MANAGE_TABS = ('questions', 'sessions', 'settings', 'import')

class StudentEntry:
    """What a student code opens: one Quiz Bank offered by a Class Session."""

    def __init__(self, code, quiz_bank, class_session, offer):
        self.code = code
        self.quiz_bank = quiz_bank
        self.class_session = class_session
        self.offer = offer

    @property
    def take_key(self):
        """Key for Take continuity (Flask session and browser storage): one per code and Quiz Bank."""
        return f'{self.code}-{self.quiz_bank.id}'

    @property
    def time_limit_minutes(self):
        return self.offer.time_limit_minutes

    def status(self, now=None):
        return class_session_rules.status(self.class_session, now or datetime.utcnow())

    @property
    def ends_at(self):
        """The effective end (UTC) students work against."""
        return class_session_rules.effective_end(self.class_session)

    def ends_in_seconds(self, now=None):
        """Whole seconds from now to the effective end (0 when past).
        The take page counts the Class Session clock from this, so a wrong device clock does not matter."""
        return max(0, int((self.ends_at - (now or datetime.utcnow())).total_seconds()))

    def page_context(self):
        """Template values shared by the start, play, wait and ended pages."""
        return {
            'quiz_bank': self.quiz_bank,
            'class_session': self.class_session,
            'student_code': self.code,
            'take_key': self.take_key,
            'time_limit_minutes': self.time_limit_minutes,
            'session_ends_at': self.ends_at,
            'session_ends_in': self.ends_in_seconds(),
        }


def find_student_entry(code, quiz_bank_id=None):
    """Resolve a student code to a StudentEntry, or 404. `quiz_bank_id` picks one offered Quiz Bank
    (default: the first one by position)."""
    class_session = ClassSession.query.filter_by(code=code).first_or_404()
    offers = class_session.offers
    if quiz_bank_id not in (None, ''):
        try:
            wanted = int(quiz_bank_id)
        except (TypeError, ValueError):
            abort(404)
        offers = [o for o in offers if o.quiz_bank_id == wanted]
    if not offers:
        abort(404)
    return StudentEntry(code, offers[0].quiz_bank, class_session, offers[0])


def render_class_session_gate(entry, status):
    """The 這堂課還沒開始 (status SOON) or 這堂課已經結束 page. Refused, so 403."""
    now = datetime.utcnow()
    class_session = entry.class_session
    starts_in = max(0, int((class_session.starts_at - now).total_seconds())) if status == class_session_rules.SOON else None
    return render_template(
        'class_session_gate.html',
        status=status,
        starts_in=starts_in,
        course_open=class_session_rules.course_is_open(class_session.course, now),
        **entry.page_context(),
    ), 403


def refuse_outside_window(entry):
    """JSON refusal for draw/start when the Class Session is not live, else None."""
    status = entry.status()
    if status == class_session_rules.LIVE:
        return None
    message = '這堂課還沒開始' if status == class_session_rules.SOON else '這堂課已經結束'
    return jsonify({'error': message, 'status': status}), 403


def render_class_session_hub(entry):
    """The 課堂清單 page: a Class Session with several Quiz Banks, any order, one Hand-in each (#12)."""
    items = []
    for offer in entry.class_session.offers:
        bank = offer.quiz_bank
        if bank.quiz_mode == 'practice':
            size = f'隨機抽 {bank.session_question_count or 10} 題'
        else:
            size = f'{Question.query.filter_by(quiz_bank_id=bank.id).count()} 題'
        limit = f'時限 {offer.time_limit_minutes} 分鐘' if offer.time_limit_minutes else '不限時'
        items.append({
            'bank': bank,
            'facts': f'{size} · {limit}',
            'url': url_for('take_quiz', code=entry.code, bank=bank.id),
        })
    return render_template('class_session_hub.html', items=items, **entry.page_context())


@app.route('/quiz/<code>')
def take_quiz(code):
    entry = find_student_entry(code, request.args.get('bank'))
    status = entry.status()
    if status != class_session_rules.LIVE:
        return render_class_session_gate(entry, status)
    if len(entry.class_session.offers) > 1 and request.args.get('bank') in (None, ''):
        return render_class_session_hub(entry)
    quiz_bank = entry.quiz_bank

    if quiz_bank.quiz_mode == 'practice':
        practice_mode, practice_total = get_bank_scoring(quiz_bank)
        return render_template(
            'practice_landing.html',
            category_ratios=get_category_ratios(quiz_bank),
            question_count=quiz_bank.session_question_count or 10,
            # Explicit points depend on the draw, so the start page cannot know the total yet.
            total_points=practice_total if practice_mode == 'average' else None,
            **entry.page_context(),
        )

    questions, _take_order = load_fixed_take_questions(entry.take_key, quiz_bank.id)
    scoring_mode, scoring_total = get_bank_scoring(quiz_bank)
    points_map = effective_points_map(questions, scoring_mode, scoring_total)
    questions_data = build_questions_data(questions, points_map)
    return render_template('take_quiz.html', questions=questions_data, is_practice=False, **entry.page_context())

@app.route('/quiz/<code>/play')
def play_quiz(code):
    entry = find_student_entry(code, request.args.get('bank'))
    status = entry.status()
    if status != class_session_rules.LIVE:
        return render_class_session_gate(entry, status)
    quiz_bank = entry.quiz_bank
    session_data = session.get(get_practice_session_key(entry.take_key))
    scoring_mode, scoring_total = get_bank_scoring(quiz_bank)

    if quiz_bank.quiz_mode == 'practice':
        if not session_data or not session_data.get('question_ids'):
            return redirect(url_for('take_quiz', code=code, bank=request.args.get('bank')))

        loaded = Question.query.filter(Question.id.in_(session_data['question_ids'])).all()
        questions = questions_in_id_order(loaded, session_data['question_ids'])
        points_map = effective_points_map(questions, scoring_mode, scoring_total)
        questions_data = build_questions_data(questions, points_map)
        return render_template(
            'take_quiz.html',
            questions=questions_data,
            is_practice=True,
            draw_warnings=session_data.get('warnings', []),
            **entry.page_context(),
        )

    questions, _take_order = load_fixed_take_questions(entry.take_key, quiz_bank.id)
    points_map = effective_points_map(questions, scoring_mode, scoring_total)
    questions_data = build_questions_data(questions, points_map)
    return render_template('take_quiz.html', questions=questions_data, is_practice=False, **entry.page_context())


@app.route('/api/quiz/<code>/status')
def take_status(code):
    """The Class Session end as the take page needs it (spec #2 C5, story 90).

    The take page polls this, so 結束課程, 立即結束, 延長 and 重新開放 made during a Take reach its clock.
    `ends_in` counts seconds from the server's now, so a wrong device clock does not matter.
    """
    entry = find_student_entry(code, request.args.get('bank'))
    now = datetime.utcnow()
    status = entry.status(now)
    ended = status == class_session_rules.DONE
    return jsonify({
        'status': status,
        'ended': ended,
        'ends_in': 0 if ended else entry.ends_in_seconds(now),
        'ends_hm': format_wall_clock_utc8(entry.ends_at, '%H:%M'),
    })

# API 路由
@app.route('/api/quiz-bank/<int:quiz_bank_id>', methods=['DELETE'])
@teacher_required
def delete_quiz_bank(quiz_bank_id):
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)

    submission_count = Submission.query.filter_by(quiz_bank_id=quiz_bank_id).count()
    payload = request.get_json(silent=True) or {}
    confirmed = payload.get('confirm') is True

    if submission_count > 0 and not confirmed:
        return jsonify({
            'error': f'此題庫已有 {submission_count} 筆作答紀錄，確認後將一併永久刪除',
            'requires_confirm': True,
            'submission_count': submission_count,
        }), 409

    try:
        session_ids = [o.class_session_id for o in quiz_bank.offers]
        db.session.delete(quiz_bank)
        db.session.flush()
        # A Class Session left with no Quiz Bank goes too (spec #2, ticket 11).
        for class_session in ClassSession.query.filter(ClassSession.id.in_(session_ids)).all():
            if not ClassSessionBank.query.filter_by(class_session_id=class_session.id).count():
                db.session.delete(class_session)
        db.session.commit()
        return jsonify({'message': '題庫已成功刪除'})
    except Exception:
        db.session.rollback()
        return jsonify({'error': '刪除失敗，請稍後再試'}), 500

@app.route('/api/quiz-bank/<int:quiz_bank_id>/questions', methods=['GET', 'POST'])
@teacher_required
def manage_questions(quiz_bank_id):
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)
    
    if request.method == 'GET':
        questions = Question.query.filter_by(quiz_bank_id=quiz_bank_id).order_by(Question.order_index).all()
        questions_data = []
        for q in questions:
            question_data = {
                'id': q.id,
                'title': q.title,
                'question_text': q.question_text,
                'question_type': q.question_type,
                'points': q.points,
                'order_index': q.order_index,
                'category': q.category or '',
            }
            if q.question_data:
                question_data['question_data'] = json.loads(q.question_data)
            questions_data.append(question_data)
        return jsonify(questions_data)
    
    elif request.method == 'POST':
        data = request.get_json() or {}
        points, points_error = parse_points(data.get('points', 1))
        if points_error:
            return jsonify({'error': points_error}), 400

        question_payload, payload_error = validate_question_data_payload(data.get('question_data', {}))
        if payload_error:
            return jsonify({'error': payload_error}), 400

        # 獲取最大的order_index
        max_order = db.session.query(db.func.max(Question.order_index)).filter_by(quiz_bank_id=quiz_bank_id).scalar() or 0
        
        question = Question(
            title=data.get('title'),
            question_text=data.get('question_text'),
            question_type=data.get('question_type'),
            question_data=json.dumps(question_payload),
            points=points,
            order_index=max_order + 1,
            category=data.get('category'),
            quiz_bank_id=quiz_bank_id
        )
        
        db.session.add(question)
        db.session.commit()
        
        return jsonify({'message': '題目新增成功', 'question_id': question.id})

@app.route('/api/question/<int:question_id>', methods=['PUT', 'DELETE'])
@teacher_required
def manage_question(question_id):
    question = owned_or_404(Question, question_id)
    quiz_bank = question.quiz_bank
    
    if request.method == 'PUT':
        data = request.get_json() or {}
        if 'points' in data:
            points, points_error = parse_points(data.get('points'))
            if points_error:
                return jsonify({'error': points_error}), 400
            question.points = points
        question.title = data.get('title', question.title)
        question.question_text = data.get('question_text', question.question_text)
        question.question_type = data.get('question_type', question.question_type)
        if 'question_data' in data:
            question_payload, payload_error = validate_question_data_payload(data.get('question_data', {}))
            if payload_error:
                return jsonify({'error': payload_error}), 400
            question.question_data = json.dumps(question_payload)
        question.category = data.get('category', question.category)
        
        db.session.commit()
        return jsonify({'message': '題目更新成功'})
    
    elif request.method == 'DELETE':
        db.session.delete(question)
        db.session.commit()
        return jsonify({'message': '題目刪除成功'})

@app.route('/api/question/<int:question_id>/copy', methods=['POST'])
@teacher_required
def copy_question(question_id):
    """Add a new Question with the same content right after the source."""
    source = owned_or_404(Question, question_id)

    position = source.order_index or 0
    Question.query.filter(
        Question.quiz_bank_id == source.quiz_bank_id,
        Question.order_index > position,
    ).update({Question.order_index: Question.order_index + 1}, synchronize_session=False)

    copy = Question(
        title=source.title,
        question_text=source.question_text,
        question_type=source.question_type,
        question_data=source.question_data,
        points=source.points,
        order_index=position + 1,
        category=source.category,
        quiz_bank_id=source.quiz_bank_id,
    )
    db.session.add(copy)
    db.session.commit()
    return jsonify({'message': '題目已複製', 'question_id': copy.id})

@app.route('/api/quiz-bank/<int:quiz_bank_id>/practice-config', methods=['PUT'])
@teacher_required
def update_practice_config(quiz_bank_id):
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)

    data = request.get_json() or {}
    quiz_mode = data.get('quiz_mode', quiz_bank.quiz_mode or 'fixed')
    session_question_count = int(data.get('session_question_count', quiz_bank.session_question_count or 10))
    category_ratios = data.get('category_ratios', get_category_ratios(quiz_bank))
    scoring_mode = (data.get('scoring_mode') or quiz_bank.scoring_mode or 'explicit').strip().lower()
    raw_scoring_total = data.get('scoring_total_points', quiz_bank.scoring_total_points)

    if quiz_mode not in ('fixed', 'practice'):
        return jsonify({'error': 'quiz_mode 無效'}), 400
    if session_question_count <= 0:
        return jsonify({'error': '每次出題數必須大於 0'}), 400
    if scoring_mode not in ('explicit', 'average'):
        return jsonify({'error': '計分模式無效'}), 400
    try:
        scoring_total_points = float(raw_scoring_total if raw_scoring_total is not None else 100)
    except (TypeError, ValueError):
        return jsonify({'error': '總分必須是數字'}), 400
    if scoring_total_points <= 0:
        return jsonify({'error': '總分必須大於 0'}), 400

    if quiz_mode == 'practice':
        errors = validate_category_ratios(category_ratios)
        if errors:
            return jsonify({'error': errors[0], 'errors': errors}), 400

    quiz_bank.quiz_mode = quiz_mode
    quiz_bank.session_question_count = session_question_count
    quiz_bank.category_ratios = json.dumps(category_ratios) if quiz_mode == 'practice' else None
    quiz_bank.scoring_mode = scoring_mode
    quiz_bank.scoring_total_points = scoring_total_points
    db.session.commit()

    return jsonify({
        'message': '練習設定已更新',
        'quiz_mode': quiz_bank.quiz_mode,
        'session_question_count': quiz_bank.session_question_count,
        'category_ratios': get_category_ratios(quiz_bank),
        'scoring_mode': quiz_bank.scoring_mode,
        'scoring_total_points': quiz_bank.scoring_total_points,
    })

@app.route('/api/quiz/<code>/draw', methods=['POST'])
def draw_practice_quiz(code):
    data = request.get_json(silent=True) or {}
    entry = find_student_entry(code, data.get('quiz_bank_id'))
    refusal = refuse_outside_window(entry)
    if refusal:
        return refusal
    quiz_bank = entry.quiz_bank
    if quiz_bank.quiz_mode != 'practice':
        return jsonify({'error': '此題庫不是練習模式'}), 400

    all_questions = Question.query.filter_by(quiz_bank_id=quiz_bank.id).all()
    selected, warnings = draw_practice_questions(quiz_bank, all_questions)
    if not selected:
        return jsonify({'error': warnings[0] if warnings else '無法抽題', 'warnings': warnings}), 400

    question_ids = [q.id for q in selected]
    session[get_practice_session_key(entry.take_key)] = {
        'question_ids': question_ids,
        'warnings': warnings,
    }

    return jsonify({
        'message': '抽題成功',
        'question_count': len(question_ids),
        'warnings': warnings,
        'redirect': url_for('play_quiz', code=code, bank=quiz_bank.id),
    })

@app.route('/api/import-quiz-md/preview', methods=['POST'])
@teacher_required
def preview_import_quiz_md():
    try:
        uploaded = request.files.get('file')
        if not uploaded or not uploaded.filename:
            return jsonify({'success': False, 'errors': ['請上傳 .md 檔案']}), 400

        content = uploaded.read().decode('utf-8-sig')
        parsed = parse_md_quiz(content)
    except Exception as exc:
        return jsonify({'success': False, 'errors': [f'解析失敗：{exc}']}), 500
    preview_questions = parsed['rows']
    if parsed['errors']:
        return jsonify({
            'success': False,
            'errors': parsed['errors'],
            'file_errors': parsed['file_errors'],
            'questions': preview_questions,
            'question_count': len(preview_questions),
        }), 400

    return jsonify({
        'success': True,
        'bank': parsed['bank'],
        'questions': preview_questions,
        'question_count': len(preview_questions),
    })

@app.route('/api/import-quiz-md/confirm', methods=['POST'])
@teacher_required
def confirm_import_quiz_md():
    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename:
        return jsonify({'success': False, 'errors': ['請上傳 .md 檔案']}), 400

    folder, refused = owned_folder_or_error(request.form.get('folder_id'))
    if refused:
        return refused

    content = uploaded.read().decode('utf-8-sig')
    parsed = parse_md_quiz(content)
    if parsed['errors']:
        return jsonify({'success': False, 'errors': parsed['errors']}), 400

    try:
        quiz_bank = create_quiz_bank_from_data(current_teacher().user_id, parsed['bank'])
        quiz_bank.folder_id = folder.id if folder else None
        create_questions_for_bank(quiz_bank.id, parsed['questions'])
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'errors': ['匯入失敗，請稍後再試']}), 500

    return jsonify({
        'success': True,
        'message': '題庫匯入成功',
        'quiz_bank_id': quiz_bank.id,
        'question_count': len(parsed['questions']),
    })

@app.route('/api/import-quiz-md/template')
@teacher_required
def download_import_template():
    return send_from_directory('static/templates', 'quiz_template.md', as_attachment=True)

@app.route('/api/quiz-bank/import-md/questions-template')
@teacher_required
def download_append_questions_template():
    return send_from_directory('static/templates', 'quiz_questions_append.md', as_attachment=True)

@app.route('/api/quiz-bank/<int:quiz_bank_id>/import-md/preview', methods=['POST'])
@teacher_required
def preview_append_quiz_md(quiz_bank_id):
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)

    try:
        uploaded = request.files.get('file')
        if not uploaded or not uploaded.filename:
            return jsonify({'success': False, 'errors': ['請上傳 .md 檔案']}), 400

        content = uploaded.read().decode('utf-8-sig')
        existing_categories = list(get_category_ratios(quiz_bank).keys())
        parsed = parse_md_questions_append(
            content,
            quiz_mode=quiz_bank.quiz_mode or 'fixed',
            existing_categories=existing_categories,
        )
    except Exception as exc:
        return jsonify({'success': False, 'errors': [f'解析失敗：{exc}']}), 500

    if parsed['errors']:
        return jsonify({
            'success': False,
            'errors': parsed['errors'],
            'warnings': parsed.get('warnings', []),
            'file_errors': parsed['file_errors'],
            'questions': parsed['rows'],
            'question_count': len(parsed['rows']),
        }), 400

    return jsonify({
        'success': True,
        'questions': parsed['rows'],
        'question_count': len(parsed['questions']),
        'warnings': parsed.get('warnings', []),
    })

@app.route('/api/quiz-bank/<int:quiz_bank_id>/import-md/confirm', methods=['POST'])
@teacher_required
def confirm_append_quiz_md(quiz_bank_id):
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)

    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename:
        return jsonify({'success': False, 'errors': ['請上傳 .md 檔案']}), 400

    content = uploaded.read().decode('utf-8-sig')
    existing_categories = list(get_category_ratios(quiz_bank).keys())
    parsed = parse_md_questions_append(
        content,
        quiz_mode=quiz_bank.quiz_mode or 'fixed',
        existing_categories=existing_categories,
    )
    if parsed['errors']:
        return jsonify({'success': False, 'errors': parsed['errors'], 'warnings': parsed.get('warnings', [])}), 400

    try:
        max_order = db.session.query(db.func.max(Question.order_index)).filter_by(
            quiz_bank_id=quiz_bank_id
        ).scalar() or 0
        create_questions_for_bank(quiz_bank_id, parsed['questions'], start_order=max_order + 1)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'errors': ['追加失敗，請稍後再試']}), 500

    total_questions = Question.query.filter_by(quiz_bank_id=quiz_bank_id).count()
    return jsonify({
        'success': True,
        'message': '題目追加成功',
        'question_count': len(parsed['questions']),
        'total_questions': total_questions,
        'warnings': parsed.get('warnings', []),
    })

@app.route('/api/quiz/<code>/submit', methods=['POST'])
def submit_quiz(code):
    data = request.get_json(silent=True) or {}
    # A hand-in names its Quiz Bank; there is no fallback to the first offered one.
    ClassSession.query.filter_by(code=code).first_or_404()
    if data.get('quiz_bank_id') in (None, ''):
        return jsonify({'error': '缺少題庫，請重新開啟測驗'}), 400
    entry = find_student_entry(code, data.get('quiz_bank_id'))
    now = datetime.utcnow()
    if now < entry.class_session.starts_at:
        return jsonify({'error': '這堂課還沒開始，不能交卷', 'status': class_session_rules.SOON}), 403
    if not class_session_rules.accepts_hand_in(entry.class_session, now):
        # Nothing is stored (spec #2 "Window check").
        return jsonify({'error': LATE_HAND_IN_ERROR, 'status': class_session_rules.DONE}), 403
    quiz_bank = entry.quiz_bank

    student_name = data.get('student_name')
    student_email = data.get('student_email', '')
    answers = data.get('answers', {})

    if not student_name:
        return jsonify({'error': '請輸入姓名'}), 400

    is_practice = quiz_bank.quiz_mode == 'practice'
    practice_session_key = get_practice_session_key(entry.take_key)
    take_session_key = get_take_session_key(entry.take_key)
    practice_session = session.get(practice_session_key) if is_practice else None

    if is_practice:
        if not practice_session or not practice_session.get('question_ids'):
            return jsonify({'error': '練習場次已失效，請重新開始練習'}), 400
        take_order = list(practice_session['question_ids'])
        loaded = Question.query.filter(Question.id.in_(take_order)).all()
        questions = questions_in_id_order(loaded, take_order)
    else:
        bank_questions = Question.query.filter_by(quiz_bank_id=quiz_bank.id).order_by(Question.order_index).all()
        bank_ids = [q.id for q in bank_questions]
        take_order = resolve_fixed_take_order_for_submit(entry.take_key, bank_ids)
        questions = questions_in_id_order(bank_questions, take_order)

    scoring_mode, scoring_total = get_bank_scoring(quiz_bank)
    points_map = effective_points_map(questions, scoring_mode, scoring_total)
    total_points = sum(points_map.values()) if points_map else 0
    score = 0
    for question in questions:
        user_answer = answers.get(str(question.id))
        score += grade_question(question, user_answer, points=points_map.get(question.id))

    # Elapsed Time is stored for every Submission, with or without a Time Limit (spec #2 "Schema").
    elapsed_seconds = None
    raw_elapsed = data.get('elapsed_seconds')
    if raw_elapsed is not None and raw_elapsed != '':
        try:
            elapsed_seconds = int(raw_elapsed)
        except (TypeError, ValueError):
            return jsonify({'error': '所花時間無效'}), 400
        if elapsed_seconds < 0:
            return jsonify({'error': '所花時間無效'}), 400

    review_flags = normalize_review_flag_ids(
        data.get('review_flag_question_ids'),
        take_order,
    )

    submission = Submission(
        student_name=student_name,
        student_email=student_email,
        answers=json.dumps(answers),
        score=score,
        total_points=total_points,
        quiz_bank_id=quiz_bank.id,
        is_practice=is_practice,
        session_question_ids=json.dumps(take_order),
        review_flag_question_ids=json.dumps(review_flags),
        scoring_mode=scoring_mode,
        scoring_total_points=scoring_total,
        elapsed_seconds=elapsed_seconds,
        class_session_id=entry.class_session.id,
    )

    db.session.add(submission)
    db.session.commit()

    if is_practice:
        session.pop(practice_session_key, None)
    session.pop(take_session_key, None)

    return jsonify({
        'message': '測驗提交成功',
        'score': score,
        'total_points': total_points,
        'percentage': round((score / total_points * 100) if total_points > 0 else 0, 2),
        'submission_id': submission.id,
        'result_url': url_for('view_result', result_token=submission.result_token),
        'is_practice': is_practice,
        'retry_url': url_for('take_quiz', code=code, bank=quiz_bank.id) if is_practice else None,
        'elapsed_seconds': submission.elapsed_seconds,
    })

@app.route('/result/<result_token>')
def view_result(result_token):
    """The student's Result Link (ADR 0008). A numeric submission id never opens a result here."""
    submission = Submission.query.filter_by(result_token=result_token).first_or_404()
    return render_submission_result(submission)

@app.route('/quiz-bank/<int:quiz_bank_id>/submissions/<int:submission_id>')
@teacher_required
def view_submission_as_teacher(quiz_bank_id, submission_id):
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)
    submission = Submission.query.filter_by(id=submission_id, quiz_bank_id=quiz_bank.id).first_or_404()
    return render_submission_result(submission, teacher_view=True)

def render_submission_result(submission, teacher_view=False):
    if submission.session_question_ids:
        question_ids = json.loads(submission.session_question_ids)
        loaded = Question.query.filter(Question.id.in_(question_ids)).all()
        questions = questions_in_id_order(loaded, question_ids)
    else:
        questions = Question.query.filter_by(quiz_bank_id=submission.quiz_bank_id).order_by(Question.order_index).all()

    student_answers = json.loads(submission.answers) if submission.answers else {}
    review_flag_ids = set(parse_review_flag_ids(getattr(submission, 'review_flag_question_ids', None)))
    snap_mode = getattr(submission, 'scoring_mode', None) or 'explicit'
    snap_total = getattr(submission, 'scoring_total_points', None)
    if snap_total is None:
        # Legacy rows: prefer the attempt's stored total over a hardcoded 100.
        # Use explicit None check so a legitimate 0 total is preserved.
        snap_total = submission.total_points if submission.total_points is not None else 100
    question_points = effective_points_map(questions, snap_mode, snap_total)
    # Right or wrong comes from the same judgement as the score (points=1 so a 0-point question still counts).
    correct_ids = {
        q.id for q in questions
        if grade_question(q, student_answers.get(str(q.id)), points=1) > 0
    }
    return render_template(
        'result.html',
        submission=submission,
        questions=questions,
        student_answers=student_answers,
        question_points=question_points,
        review_flag_ids=review_flag_ids,
        correct_ids=correct_ids,
        teacher_view=teacher_view,
    )

@app.route('/quiz-bank/<int:quiz_bank_id>/submissions')
@teacher_required
def view_submissions_page(quiz_bank_id):
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)
    
    return render_template('submissions.html', quiz_bank=quiz_bank,
                           pass_percent=grade_stats.PASS_PERCENT, high_percent=grade_stats.HIGH_PERCENT,
                           class_session_options=grade_class_session_options(quiz_bank),
                           selected_class_session=request.args.get('class_session', ''))

@app.route('/api/quiz-bank/<int:quiz_bank_id>/submissions')
@teacher_required
def view_submissions(quiz_bank_id):
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)
    
    submissions = Submission.query.filter_by(quiz_bank_id=quiz_bank_id).order_by(Submission.submitted_at.desc()).all()
    submissions_data = []
    
    for s in submissions:
        submissions_data.append({
            'id': s.id,
            'student_name': s.student_name,
            'student_email': s.student_email,
            'score': s.score,
            'total_points': s.total_points,
            'percentage': round((s.score / s.total_points * 100) if s.total_points > 0 else 0, 2),
            'submitted_at': format_wall_clock_utc8(s.submitted_at, '%Y-%m-%d %H:%M:%S'),
            'is_practice': bool(s.is_practice),
            'elapsed_seconds': s.elapsed_seconds,
        })
    
    return jsonify(submissions_data)

@app.route('/api/submission/<int:submission_id>', methods=['DELETE'])
@teacher_required
def delete_submission(submission_id):
    submission = owned_or_404(Submission, submission_id)
    quiz_bank = submission.quiz_bank
    
    try:
        db.session.delete(submission)
        db.session.commit()
        return jsonify({'message': '成績已成功刪除'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '刪除失敗，請稍後再試'}), 500

# ===== Grades page (ticket 15, issue #17). Number rules live in grade_stats.py. =====

CSV_BOM = chr(0xFEFF)  # lets Excel read the UTF-8 CSV

def grade_class_session_options(quiz_bank, now=None):
    """Class Sessions for the 成績 filter: those offering the Quiz Bank, then any other one
    that still holds its Submissions. Each: id, name, status, status_label."""
    now = now or datetime.utcnow()
    sessions = [row['session'] for row in quiz_bank_class_sessions(quiz_bank, now)]
    known = {cs.id for cs in sessions}
    extra_ids = {cs_id for (cs_id,) in db.session.query(Submission.class_session_id)
                 .filter(Submission.quiz_bank_id == quiz_bank.id,
                         Submission.class_session_id.isnot(None)).distinct()} - known
    if extra_ids:
        sessions += ClassSession.query.filter(ClassSession.id.in_(extra_ids),
                                              ClassSession.teacher_id == quiz_bank.teacher_id).all()
    options = []
    for cs in sessions:
        status = class_session_rules.status(cs, now)
        options.append({'id': cs.id, 'name': cs.name, 'course': cs.course.name, 'status': status,
                        'status_label': class_session_status_label(cs, status, now)})
    return options


def grade_filter_session(quiz_bank):
    """The Class Session named by ?class_session=, None for all; 404 when it is not the Teacher's."""
    raw = request.args.get('class_session', '')
    if raw in ('', 'all'):
        return None
    class_session = ClassSession.query.get(int(raw)) if raw.isdigit() else None
    if class_session is None or class_session.teacher_id != quiz_bank.teacher_id:
        abort(404)
    return class_session


def quiz_bank_grades(quiz_bank, class_session=None, query=''):
    """Everything the 成績 page shows: stats, bands and most missed follow the Class Session filter;
    the name search narrows only the rows. Rows are ranked by percent, highest first."""
    all_subs = (Submission.query.filter_by(quiz_bank_id=quiz_bank.id)
                .order_by(Submission.submitted_at, Submission.id).all())
    takes = grade_stats.take_numbers(
        (s.id, s.student_name, s.class_session_id, s.quiz_bank_id, s.submitted_at) for s in all_subs)
    subs = [s for s in all_subs if class_session is None or s.class_session_id == class_session.id]
    limits = {o.class_session_id: o.time_limit_minutes
              for o in ClassSessionBank.query.filter_by(quiz_bank_id=quiz_bank.id)}
    questions = Question.query.filter_by(quiz_bank_id=quiz_bank.id).order_by(Question.order_index).all()
    by_id = {q.id: q for q in questions}
    number = {q.id: i for i, q in enumerate(questions, start=1)}

    judgements = []
    for s in subs:
        answers = json.loads(s.answers) if s.answers else {}
        take_order = json.loads(s.session_question_ids) if s.session_question_ids else list(by_id)
        for qid in take_order:
            question = by_id.get(qid)
            if question is not None:  # same judgement as the result page (render_submission_result)
                judgements.append((qid, grade_question(question, answers.get(str(qid)), points=1) > 0))
    missed = grade_stats.most_missed(judgements)
    for row in missed:
        question = by_id[row['question_id']]
        row.update(number=number[question.id], title=question.title, question_type=question.question_type,
                   type_name=get_question_type_name(question.question_type))

    percents = {s.id: grade_stats.percent(s.score, s.total_points) for s in subs}
    ranked = sorted(subs, key=lambda s: -percents[s.id])  # stable: earlier hand-in first on a tie
    needle = query.strip().casefold()
    rows = []
    for rank, s in enumerate(ranked, start=1):
        if needle and needle not in (s.student_name or '').casefold():
            continue
        limit = limits.get(s.class_session_id)
        take, n_takes = takes[s.id]
        rows.append({
            'id': s.id, 'rank': rank,
            'student_name': s.student_name, 'student_email': s.student_email,
            'class_session_id': s.class_session_id,
            'class_session': s.class_session.name if s.class_session else '',
            'take': take, 'takes': n_takes,
            'score': s.score, 'total_points': s.total_points, 'percentage': percents[s.id],
            'elapsed_seconds': s.elapsed_seconds,
            'time_up': grade_stats.is_time_up(s.elapsed_seconds, limit),
            'is_practice': bool(s.is_practice),
            'submitted_at': format_wall_clock_utc8(s.submitted_at, '%Y-%m-%d %H:%M:%S'),
        })
    return {
        'stats': grade_stats.summary(list(percents.values()), [s.student_name for s in subs]),
        'bands': grade_stats.bands(percents.values()),
        'most_missed': missed,
        'submissions': rows,
    }


@app.route('/api/quiz-bank/<int:quiz_bank_id>/grades')
@teacher_required
def quiz_bank_grades_api(quiz_bank_id):
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)
    data = quiz_bank_grades(quiz_bank, grade_filter_session(quiz_bank), request.args.get('q', ''))
    data['class_sessions'] = grade_class_session_options(quiz_bank)
    return jsonify(data)


@app.route('/quiz-bank/<int:quiz_bank_id>/submissions.csv')
@teacher_required
def export_submissions_csv(quiz_bank_id):
    """The filtered Submissions (Class Session and name search) as CSV, in the table's order."""
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)
    data = quiz_bank_grades(quiz_bank, grade_filter_session(quiz_bank), request.args.get('q', ''))
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['名次', '姓名', 'Email', '課堂', '第幾次', '得分', '總分', '百分比', '用時', '時間到', '交卷時間'])
    for r in data['submissions']:
        writer.writerow([r['rank'], r['student_name'], r['student_email'] or '', r['class_session'], r['take'],
                         f"{r['score']:g}", f"{r['total_points']:g}", f"{r['percentage']:.1f}",
                         grade_stats.elapsed_text(r['elapsed_seconds']), '時間到' if r['time_up'] else '',
                         r['submitted_at']])
    response = app.response_class(CSV_BOM + out.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = "attachment; filename*=UTF-8''" + quote(f'{quiz_bank.title}_成績.csv')
    return response


# ===== Grade sheets: 課堂總表 and 課程總表 (ticket 16, issue #18). Rules live in grade_sheets.py. =====

app.jinja_env.globals.update(grade_whole_percent=grade_sheets.whole_percent, grade_band=grade_sheets.band)


def _sheet_hand_ins(class_session_ids):
    subs = Submission.query.filter(Submission.class_session_id.in_(class_session_ids)).all() if class_session_ids else []
    return [{'id': s.id, 'name': s.student_name, 'class_session_id': s.class_session_id,
             'quiz_bank_id': s.quiz_bank_id, 'submitted_at': s.submitted_at,
             'percent': grade_stats.percent(s.score, s.total_points)} for s in subs]


def grade_sheet(class_sessions):
    """The sheet over these Class Sessions (in this order): one column per offered Quiz Bank,
    in the Class Session's order. Columns carry session, offer, handed_in and average."""
    offers = [offer for cs in class_sessions for offer in cs.offers]
    sheet = grade_sheets.build_sheet([(o.class_session_id, o.quiz_bank_id) for o in offers],
                                     _sheet_hand_ins([cs.id for cs in class_sessions]))
    for column, offer in zip(sheet['columns'], offers):
        column.update(session=offer.class_session, offer=offer, quiz_bank=offer.quiz_bank)
    return sheet


def course_sessions_in_start_order(course):
    return sorted(course.class_sessions, key=lambda cs: (cs.starts_at, cs.id))


def sheet_csv(filename, header, sheet, with_summary):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for row in sheet['rows']:
        line = [row['name']] + [v for c in row['cells'] for v in grade_sheets.csv_cells(c)]
        if with_summary:
            line += ['' if row['average'] is None else grade_sheets.whole_percent(row['average']),
                     f"{row['answered']} / {len(row['cells'])}"]
        writer.writerow(line)
    response = app.response_class(CSV_BOM + out.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = "attachment; filename*=UTF-8''" + quote(filename)
    return response


@app.route('/class-sessions/<int:class_session_id>')
@teacher_required
def class_session_sheet(class_session_id):
    class_session = owned_or_404(ClassSession, class_session_id)
    now = datetime.utcnow()
    status = class_session_rules.status(class_session, now)
    return render_template('grade_sheet.html', kind='session', class_session=class_session,
                           course=class_session.course, status=status,
                           status_label=class_session_status_label(class_session, status),
                           course_open=class_session_rules.course_is_open(class_session.course, now),
                           sheet=grade_sheet([class_session]),
                           cs_dialog=class_session_dialog_data(current_teacher().user_id))


@app.route('/class-sessions/<int:class_session_id>/sheet.csv')
@teacher_required
def class_session_sheet_csv(class_session_id):
    class_session = owned_or_404(ClassSession, class_session_id)
    sheet = grade_sheet([class_session])
    header = ['學生'] + grade_sheets.csv_header(c['quiz_bank'].title for c in sheet['columns'])
    return sheet_csv(f'{class_session.name}_課堂總表.csv', header, sheet, with_summary=False)


@app.route('/courses/<int:course_id>')
@teacher_required
def course_sheet(course_id):
    course = owned_or_404(Course, course_id)
    now = datetime.utcnow()
    sessions = course_sessions_in_start_order(course)
    groups = [{'session': cs, 'span': len(cs.offers)} for cs in sessions if cs.offers]
    n_active, n_sessions, n_subs = course_numbers(course, now)
    course_info = {'ends_on': course_json(course, now)['ends_on'],  # what the Course actions need
                   'n_active': n_active, 'n_sessions': n_sessions, 'n_subs': n_subs}
    return render_template('grade_sheet.html', kind='course', course=course, groups=groups,
                           course_open=class_session_rules.course_is_open(course, now),
                           course_info=course_info, sheet=grade_sheet(sessions))


@app.route('/courses/<int:course_id>/sheet.csv')
@teacher_required
def course_sheet_csv(course_id):
    course = owned_or_404(Course, course_id)
    sheet = grade_sheet(course_sessions_in_start_order(course))
    header = (['學生'] + grade_sheets.csv_header(f"{c['session'].name} · {c['quiz_bank'].title}"
                                                 for c in sheet['columns'])
              + ['平均', '寫了'])
    return sheet_csv(f'{course.name}_課程總表.csv', header, sheet, with_summary=True)


# ===== Courses and Class Sessions (ticket 09, issue #11) =====
# Later tickets add their routes and helpers to this section (append; do not reorder).

def _field_error(message, field, status=400):
    return jsonify({'error': message, 'field': field}), status


def parse_time_limit(value):
    """Time Limit in whole minutes from a form value. Returns (minutes or None, error or None)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    text = str(value).strip()
    try:
        minutes = int(text)
    except (TypeError, ValueError):
        return None, '時限要是大於 0 的整數分鐘'
    if minutes <= 0:
        return None, '時限要是大於 0 的整數分鐘'
    return minutes, None


def open_courses(teacher_id, now=None):
    """The Teacher's open Courses, the last-used one (newest Class Session) first, then newest first."""
    now = now or datetime.utcnow()
    courses = Course.query.filter_by(teacher_id=teacher_id).all()
    last_used = dict(
        db.session.query(ClassSession.course_id, db.func.max(ClassSession.created_at))
        .filter(ClassSession.teacher_id == teacher_id).group_by(ClassSession.course_id).all()
    )
    open_ones = [c for c in courses if class_session_rules.course_is_open(c, now)]
    return sorted(open_ones, key=lambda c: (last_used.get(c.id) or datetime.min, c.created_at or datetime.min, c.id),
                  reverse=True)


def last_time_limits(teacher_id):
    """{quiz_bank_id: the Time Limit that Quiz Bank had in its latest Class Session (by start)}."""
    rows = (db.session.query(ClassSessionBank.quiz_bank_id, ClassSessionBank.time_limit_minutes)
            .join(ClassSession).filter(ClassSession.teacher_id == teacher_id)
            .order_by(ClassSession.starts_at.asc(), ClassSession.id.asc()).all())
    limits = {}
    for bank_id, minutes in rows:
        limits[bank_id] = minutes  # later rows win
    return limits


def class_session_dialog_data(teacher_id, current_folder_id=None):
    """Data for templates/_class_session_dialog.html: the open Courses and the pickable Quiz Banks.

    `current_folder_id` is the Folder the page shows (#12): it comes first in the bank list.
    """
    courses = open_courses(teacher_id)
    folders = teacher_folders(teacher_id)
    folders.sort(key=lambda f: f.id != current_folder_id)  # stable: the rest keep Folder page order
    limits = last_time_limits(teacher_id)
    banks = (QuizBank.query.filter_by(teacher_id=teacher_id)
             .order_by(QuizBank.created_at.desc(), QuizBank.id.desc()).all())
    question_counts = dict(
        db.session.query(Question.quiz_bank_id, db.func.count(Question.id))
        .join(QuizBank).filter(QuizBank.teacher_id == teacher_id).group_by(Question.quiz_bank_id).all()
    )
    return {
        'courses': [{
            'id': c.id, 'name': c.name,
            'ends_at': class_session_rules.to_wall_clock(c.ends_at) if c.ends_at else None,
        } for c in courses],
        'default_course_id': courses[0].id if courses else None,
        'folders': [folder_json(f) for f in folders],
        'current_folder_id': current_folder_id if any(f.id == current_folder_id for f in folders) else None,
        'banks': [{
            'id': b.id, 'title': b.title,
            'mode': quiz_mode_label(b.quiz_mode),
            'n_questions': question_counts.get(b.id, 0),
            'last_time_limit': limits.get(b.id),
            'folder_id': b.folder_id,
        } for b in banks],
    }


def class_session_json(class_session):
    return {
        'id': class_session.id,
        'code': class_session.code,
        'name': class_session.name,
        'course_id': class_session.course_id,
        'course_name': class_session.course.name,
        'url': url_for('take_quiz', code=class_session.code, _external=True),
        'starts_at': class_session_rules.to_wall_clock(class_session.starts_at),
        'ends_at': class_session_rules.to_wall_clock(class_session.ends_at),
        'banks': [{'quiz_bank_id': o.quiz_bank_id, 'time_limit_minutes': o.time_limit_minutes}
                  for o in class_session.offers],
    }


def quiz_bank_class_sessions(quiz_bank, now=None):
    """The Class Sessions that offer this Quiz Bank, live first, then upcoming (soonest first),
    then ended (latest end first). Each row: session, offer, status, status_label, n_subs, n_other_banks."""
    now = now or datetime.utcnow()
    offers = (ClassSessionBank.query.join(ClassSession)
              .filter(ClassSessionBank.quiz_bank_id == quiz_bank.id,
                      ClassSession.teacher_id == quiz_bank.teacher_id).all())
    counts = dict(
        db.session.query(Submission.class_session_id, db.func.count(Submission.id))
        .filter(Submission.quiz_bank_id == quiz_bank.id, Submission.class_session_id.isnot(None))
        .group_by(Submission.class_session_id).all()
    )
    rows = []
    for offer in offers:
        class_session = offer.class_session
        status = class_session_rules.status(class_session, now)
        rows.append({
            'session': class_session,
            'offer': offer,
            'status': status,
            'status_label': class_session_status_label(class_session, status, now),
            'n_subs': counts.get(class_session.id, 0),
            'n_other_banks': len(class_session.offers) - 1,
            'course_open': class_session_rules.course_is_open(class_session.course, now),
        })
    return sorted(rows, key=lambda r: class_session_rules.list_order(r['session'], r['status']))


def class_session_status_label(class_session, status, now=None):
    """進行中 / 即將開始 / 已結束, and 已結束（課程已結束） when the Course is not open (spec C8)."""
    now = now or datetime.utcnow()
    if status == class_session_rules.LIVE:
        return '進行中'
    if status == class_session_rules.SOON:
        return '即將開始'
    if not class_session_rules.course_is_open(class_session.course, now):
        return '已結束（課程已結束）'
    return '已結束'


@app.route('/api/courses', methods=['POST'])
@teacher_required
def create_course():
    """Create a Course. Body: name, ends_on ('YYYY-MM-DD' UTC+8 day, optional). Edit and the rest are below."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return _field_error('請輸入課程名稱', 'name')
    ends_at, error = class_session_rules.parse_course_end(data.get('ends_on'), datetime.utcnow())
    if error:
        return _field_error(error, 'ends_on')
    course = Course(teacher_id=current_teacher().user_id, name=name, ends_at=ends_at)
    db.session.add(course)
    db.session.commit()
    return jsonify(course_json(course)), 201


@app.route('/api/class-sessions', methods=['POST'])
@teacher_required
def create_class_session():
    """Open a Class Session.

    Body: course_id (an open Course) or new_course_name, name, starts_at, ends_at
    (ISO 8601; without an offset it is a UTC+8 wall clock), banks: [{quiz_bank_id, time_limit_minutes}].
    Errors: 400/403/404 with {error, field}.
    """
    data = request.get_json(silent=True) or {}
    teacher_id = current_teacher().user_id
    now = datetime.utcnow()

    course = None
    new_course_name = (data.get('new_course_name') or '').strip()
    if data.get('course_id') not in (None, '', 'new'):
        course = owned_or_none(Course, data['course_id'])
        if course is None:
            return _field_error('找不到這個課程', 'course', 404)
        if not class_session_rules.course_is_open(course, now):
            return _field_error('這個課程已經結束，不能再開課堂。請先重新開啟課程。', 'course')
    elif not new_course_name:
        return _field_error('請選擇課程，或輸入新課程的名稱', 'course')

    name = (data.get('name') or '').strip()
    if not name:
        return _field_error('請輸入課堂名稱', 'name')

    starts_at = class_session_rules.parse_wall_clock(data.get('starts_at'))
    ends_at = class_session_rules.parse_wall_clock(data.get('ends_at'))
    if starts_at is None or ends_at is None:
        return _field_error('請選好開始和結束時間', 'starts_at' if starts_at is None else 'ends_at')
    if ends_at <= starts_at:
        return _field_error('結束時間要晚於開始時間', 'ends_at')
    if ends_at <= now:
        return _field_error('結束時間已經過了，學生會打不開', 'ends_at')

    offers = []
    seen = set()
    for item in data.get('banks') or []:
        item = item if isinstance(item, dict) else {'quiz_bank_id': item}
        try:
            bank_id = int(item.get('quiz_bank_id'))
        except (TypeError, ValueError):
            return _field_error('找不到這份題庫', 'banks', 404)
        if bank_id in seen:
            continue
        quiz_bank = owned_or_none(QuizBank, bank_id)
        if quiz_bank is None:
            return _field_error('找不到這份題庫', 'banks', 404)
        minutes, error = parse_time_limit(item.get('time_limit_minutes'))
        if error:
            return _field_error(error, 'banks')
        seen.add(bank_id)
        offers.append((bank_id, minutes))
    if not offers:
        return _field_error('至少要選一份題庫', 'banks')

    if course is None:
        course = Course(teacher_id=teacher_id, name=new_course_name)
        db.session.add(course)
        db.session.flush()
    class_session = ClassSession(
        teacher_id=teacher_id, course_id=course.id, name=name,
        code=new_class_session_code(), starts_at=starts_at, ends_at=ends_at,
    )
    db.session.add(class_session)
    db.session.flush()
    for position, (bank_id, minutes) in enumerate(offers):
        db.session.add(ClassSessionBank(class_session_id=class_session.id, quiz_bank_id=bank_id,
                                        position=position, time_limit_minutes=minutes))
    db.session.commit()
    return jsonify(class_session_json(class_session)), 201


# ----- Manage Class Sessions and Courses (ticket 11, issue #13) -----

REOPEN_FOR = timedelta(minutes=30)
COURSE_ENDED_ERROR = '這個課程已經結束。請先重新開啟課程。'


def submission_counts_by_bank(class_session):
    """{quiz_bank_id: Submissions of that Quiz Bank in this Class Session}."""
    return dict(
        db.session.query(Submission.quiz_bank_id, db.func.count(Submission.id))
        .filter(Submission.class_session_id == class_session.id).group_by(Submission.quiz_bank_id).all()
    )


def class_session_edit_json(class_session, now=None):
    """class_session_json plus what the edit dialog needs: lock state and each Quiz Bank's title and count."""
    now = now or datetime.utcnow()
    counts = submission_counts_by_bank(class_session)
    data = class_session_json(class_session)
    data.update({
        'started': class_session_rules.has_started(class_session, now),
        'course_open': class_session_rules.course_is_open(class_session.course, now),
        'status': class_session_rules.status(class_session, now),
        'n_subs': sum(counts.values()),
        'banks': [{
            'quiz_bank_id': o.quiz_bank_id, 'title': o.quiz_bank.title,
            'time_limit_minutes': o.time_limit_minutes, 'n_subs': counts.get(o.quiz_bank_id, 0),
        } for o in class_session.offers],
    })
    return data


def _same_minute(a, b):
    return abs((a - b).total_seconds()) < 60


@app.route('/api/class-sessions/<int:class_session_id>', methods=['GET', 'PUT', 'DELETE'])
@teacher_required
def manage_class_session(class_session_id):
    """GET: edit data. PUT: edit (spec #2: start and Time Limits only before the start).
    DELETE: delete with its Submissions (needs {confirm: true} when it has Submissions)."""
    class_session = owned_or_404(ClassSession, class_session_id)
    now = datetime.utcnow()
    if request.method == 'GET':
        return jsonify(class_session_edit_json(class_session, now))
    data = request.get_json(silent=True) or {}
    if request.method == 'DELETE':
        n_subs = len(class_session.submissions)
        if n_subs and data.get('confirm') is not True:
            return jsonify({
                'error': f'這堂課有 {n_subs} 份作答，確認後會一起永久刪除',
                'requires_confirm': True, 'submission_count': n_subs,
            }), 409
        db.session.delete(class_session)
        db.session.commit()
        return jsonify({'message': f'已刪除課堂「{class_session.name}」'})
    return edit_class_session(class_session, data, now)


def edit_class_session(class_session, data, now):
    started = class_session_rules.has_started(class_session, now)
    if data.get('course_id') not in (None, '') and str(data.get('course_id')) != str(class_session.course_id):
        return _field_error('課堂建立後不能換課程', 'course')

    name = (data.get('name') or '').strip()
    if not name:
        return _field_error('請輸入課堂名稱', 'name')

    starts_at = class_session.starts_at
    if data.get('starts_at'):
        starts_at = class_session_rules.parse_wall_clock(data.get('starts_at'))
        if starts_at is None:
            return _field_error('請選好開始時間', 'starts_at')
        if started and not _same_minute(starts_at, class_session.starts_at):
            return _field_error('課堂已經開始，不能改開始時間', 'starts_at')
        if started:
            starts_at = class_session.starts_at
    ends_at = class_session.ends_at
    if data.get('ends_at'):
        ends_at = class_session_rules.parse_wall_clock(data.get('ends_at'))
        if ends_at is None:
            return _field_error('請選好結束時間', 'ends_at')
        if _same_minute(ends_at, class_session.ends_at):
            ends_at = class_session.ends_at
        elif not class_session_rules.course_is_open(class_session.course, now):
            return _field_error(COURSE_ENDED_ERROR, 'ends_at')  # as 延長 and 重新開放 refuse it
        elif ends_at <= now:
            return _field_error('結束時間已經過了。要現在結束，請按「立即結束」。', 'ends_at')
    if ends_at <= starts_at:
        return _field_error('結束時間要晚於開始時間', 'ends_at')

    current = {o.quiz_bank_id: o for o in class_session.offers}
    wanted = []
    for item in data.get('banks') or []:
        item = item if isinstance(item, dict) else {'quiz_bank_id': item}
        try:
            bank_id = int(item.get('quiz_bank_id'))
        except (TypeError, ValueError):
            return _field_error('找不到這份題庫', 'banks', 404)
        if any(bank_id == b for b, _ in wanted):
            continue
        if bank_id not in current:
            if owned_or_none(QuizBank, bank_id) is None:
                return _field_error('找不到這份題庫', 'banks', 404)
        minutes, error = parse_time_limit(item.get('time_limit_minutes'))
        if error:
            return _field_error(error, 'banks')
        if started and bank_id in current and minutes != current[bank_id].time_limit_minutes:
            return _field_error('課堂已經開始，不能改時限', 'banks')
        wanted.append((bank_id, minutes))
    if not wanted:
        return _field_error('至少要選一份題庫', 'banks')

    kept = {b for b, _ in wanted}
    counts = submission_counts_by_bank(class_session)
    removed = [o for b, o in current.items() if b not in kept]
    lost = sum(counts.get(o.quiz_bank_id, 0) for o in removed)
    if lost and data.get('confirm') is not True:
        return jsonify({
            'error': f'移除的題庫在這堂課有 {lost} 份作答，確認後會一起永久刪除',
            'requires_confirm': True, 'submission_count': lost,
            'removed': [{'quiz_bank_id': o.quiz_bank_id, 'title': o.quiz_bank.title,
                         'n_subs': counts.get(o.quiz_bank_id, 0)} for o in removed],
        }), 409

    for offer in removed:
        Submission.query.filter_by(class_session_id=class_session.id, quiz_bank_id=offer.quiz_bank_id).delete()
        class_session.offers.remove(offer)
    db.session.flush()
    for position, (bank_id, minutes) in enumerate(wanted):
        offer = current.get(bank_id)
        if offer is None:
            class_session.offers.append(ClassSessionBank(quiz_bank_id=bank_id, position=position,
                                                         time_limit_minutes=minutes))
        else:
            offer.position = position
            offer.time_limit_minutes = minutes
    class_session.name = name
    class_session.starts_at = starts_at
    class_session.ends_at = ends_at
    db.session.commit()
    return jsonify(class_session_edit_json(class_session, now))


@app.route('/api/class-sessions/<int:class_session_id>/<action>', methods=['POST'])
@teacher_required
def class_session_action(class_session_id, action):
    """end (a live one, now), start-now (an upcoming one, same length), extend ({minutes}, default 10;
    a live one only), reopen (an ended one, for 30 minutes). An ended Course refuses all but end."""
    if action not in ('end', 'start-now', 'extend', 'reopen'):
        return jsonify({'error': '找不到這個動作'}), 404
    class_session = owned_or_404(ClassSession, class_session_id)
    now = datetime.utcnow().replace(microsecond=0)
    status = class_session_rules.status(class_session, now)
    if action != 'end' and not class_session_rules.course_is_open(class_session.course, now):
        return _field_error(COURSE_ENDED_ERROR, 'course')

    if action == 'end':
        if status != class_session_rules.LIVE:
            return jsonify({'error': '這堂課沒有在進行'}), 400
        class_session.ends_at = now - timedelta(seconds=1)
        message = f'「{class_session.name}」已結束，學生不能再作答'
    elif action == 'start-now':
        if status != class_session_rules.SOON:
            return jsonify({'error': '只有還沒開始的課堂可以現在開始'}), 400
        length = class_session.ends_at - class_session.starts_at
        class_session.starts_at = now
        class_session.ends_at = now + length
        message = f'「{class_session.name}」現在開始'
    elif action == 'extend':
        if status == class_session_rules.DONE:
            return jsonify({'error': '這堂課已經結束，請用「重新開放」'}), 400
        if status != class_session_rules.LIVE:
            return jsonify({'error': '只有進行中的課堂可以延長。要改時間，請編輯課堂。'}), 400
        minutes, error_text = parse_time_limit((request.get_json(silent=True) or {}).get('minutes') or 10)
        if error_text:
            return jsonify({'error': '延長的時間要是大於 0 的整數分鐘'}), 400
        class_session.ends_at += timedelta(minutes=minutes)
        message = f'「{class_session.name}」延長 {minutes} 分鐘'
    else:
        if status != class_session_rules.DONE:
            return jsonify({'error': '只有已結束的課堂可以重新開放'}), 400
        class_session.ends_at = now + REOPEN_FOR
        message = f'「{class_session.name}」重新開放 {int(REOPEN_FOR.total_seconds() // 60)} 分鐘'
    db.session.commit()
    data = class_session_edit_json(class_session, now)
    data['message'] = message
    return jsonify(data)


def course_json(course, now=None):
    now = now or datetime.utcnow()
    return {
        'id': course.id, 'name': course.name,
        'ends_on': class_session_rules.to_wall_clock(course.ends_at)[:10] if course.ends_at else None,
        'ends_at': class_session_rules.to_wall_clock(course.ends_at) if course.ends_at else None,
        'open': class_session_rules.course_is_open(course, now),
    }


def course_numbers(course, now):
    """(live or upcoming Class Sessions, Class Sessions, Submissions) of a Course."""
    sessions = course.class_sessions
    active = sum(1 for s in sessions if class_session_rules.status(s, now) != class_session_rules.DONE)
    ids = [s.id for s in sessions]
    n_subs = Submission.query.filter(Submission.class_session_id.in_(ids)).count() if ids else 0
    return active, len(sessions), n_subs


@app.route('/api/courses/<int:course_id>', methods=['PUT', 'DELETE'])
@teacher_required
def manage_course(course_id):
    """PUT: rename and set or clear the end date (ends_on). DELETE: delete with its Class Sessions
    and Submissions (needs {confirm: true} when there are Submissions)."""
    course = owned_or_404(Course, course_id)
    data = request.get_json(silent=True) or {}
    now = datetime.utcnow()
    if request.method == 'DELETE':
        _, n_sessions, n_subs = course_numbers(course, now)
        if n_subs and data.get('confirm') is not True:
            return jsonify({
                'error': f'這個課程有 {n_sessions} 個課堂和 {n_subs} 份作答，確認後會一起永久刪除',
                'requires_confirm': True, 'session_count': n_sessions, 'submission_count': n_subs,
            }), 409
        db.session.delete(course)
        db.session.commit()
        return jsonify({'message': f'已刪除課程「{course.name}」'})

    name = (data.get('name') or '').strip()
    if not name:
        return _field_error('請輸入課程名稱', 'name')
    if 'ends_on' in data:
        same_day = course.ends_at is not None and str(data.get('ends_on') or '')[:10] == course_json(course)['ends_on']
        if not same_day:
            ends_at, error_text = class_session_rules.parse_course_end(data.get('ends_on'), now)
            if error_text:
                return _field_error(error_text, 'ends_on')
            course.ends_at = ends_at
    course.name = name
    db.session.commit()
    return jsonify(course_json(course, now))


@app.route('/api/courses/<int:course_id>/<action>', methods=['POST'])
@teacher_required
def course_action(course_id, action):
    """end: 結束課程 (sets ended_at; Class Session times stay). reopen: clears ended_at and a passed end date."""
    if action not in ('end', 'reopen'):
        return jsonify({'error': '找不到這個動作'}), 404
    course = owned_or_404(Course, course_id)
    now = datetime.utcnow()
    is_open = class_session_rules.course_is_open(course, now)
    if action == 'end':
        if not is_open:
            return jsonify({'error': '這個課程已經結束'}), 400
        n_ended, _, _ = course_numbers(course, now)
        course.ended_at = now
        db.session.commit()
        data = course_json(course, now)
        data.update({'n_ended': n_ended, 'message': f'課程「{course.name}」已結束'})
        return jsonify(data)
    if is_open:
        return jsonify({'error': '這個課程沒有結束'}), 400
    course.ended_at = None
    if course.ends_at is not None and course.ends_at < now:
        course.ends_at = None
    db.session.commit()
    n_back, _, _ = course_numbers(course, now)
    data = course_json(course, now)
    data.update({'n_back': n_back, 'message': (
        f'已重新開啟「{course.name}」，{n_back} 個課堂的時間還沒過，學生可以繼續作答' if n_back
        else f'已重新開啟「{course.name}」。底下課堂的時間都過了，要的話再開新課堂')})
    return jsonify(data)


SESSION_TABS = (('all', '全部'), ('live', '進行中'), ('soon', '即將開始'), ('done', '已結束'))


def class_sessions_page_data(teacher_id, status_filter='all', query='', now=None):
    """The 課堂 page: open and ended Courses, each with its matching Class Session rows, and tab counts."""
    now = now or datetime.utcnow()
    needle = query.casefold()
    courses = Course.query.filter_by(teacher_id=teacher_id).order_by(Course.created_at.desc(), Course.id.desc()).all()
    folders = {f.id: f for f in teacher_folders(teacher_id)}
    counts = {}  # (class_session_id, quiz_bank_id) -> Submissions
    for session_id, bank_id, n in (db.session.query(Submission.class_session_id, Submission.quiz_bank_id,
                                                    db.func.count(Submission.id))
                                   .join(ClassSession).filter(ClassSession.teacher_id == teacher_id)
                                   .group_by(Submission.class_session_id, Submission.quiz_bank_id).all()):
        counts[(session_id, bank_id)] = n
    tab_counts = {key: 0 for key, _ in SESSION_TABS}
    open_blocks, ended_blocks = [], []
    for course in courses:
        is_open = class_session_rules.course_is_open(course, now)
        rows = []
        for class_session in course.class_sessions:
            status = class_session_rules.status(class_session, now)
            banks = [{
                'title': o.quiz_bank.title, 'time_limit': o.time_limit_minutes,
                'n_subs': counts.get((class_session.id, o.quiz_bank_id), 0),
                'folder': folders.get(o.quiz_bank.folder_id),
            } for o in class_session.offers]
            rows.append({'session': class_session, 'status': status, 'banks': banks,
                         'status_label': class_session_status_label(class_session, status, now)})
            if is_open:
                tab_counts['all'] += 1
                tab_counts[status] += 1
        rows.sort(key=lambda r: class_session_rules.list_order(r['session'], r['status']))
        text = lambda row: ' '.join([course.name, row['session'].name, row['session'].code]
                                    + [b['title'] for b in row['banks']]).casefold()
        shown = [r for r in rows if (status_filter == 'all' or r['status'] == status_filter)
                 and (not needle or needle in text(r))]
        if not shown and not (status_filter == 'all' and (not needle or needle in course.name.casefold())):
            continue
        block = {
            'course': course, 'open': is_open, 'rows': shown, 'n_sessions': len(rows),
            'ends_on': course_json(course, now)['ends_on'],
            'n_live': sum(1 for r in rows if r['status'] == class_session_rules.LIVE),
            'n_active': sum(1 for r in rows if r['status'] != class_session_rules.DONE),
            'n_subs': sum(sum(b['n_subs'] for b in r['banks']) for r in rows),
        }
        (open_blocks if is_open else ended_blocks).append(block)
    return {'open_courses': open_blocks, 'ended_courses': ended_blocks, 'counts': tab_counts,
            'n_courses': len(courses)}


@app.template_global()
def course_end_text(course):
    """到 12/31 23:59 / 已在 11/27 結束 / 沒有結束日期 (UTC+8)."""
    return class_session_rules.course_end_text(course, datetime.utcnow())


@app.route('/class-sessions')
@teacher_required
def class_sessions():
    teacher_id = current_teacher().user_id
    status_filter = request.args.get('status') or 'all'
    if status_filter not in dict(SESSION_TABS):
        status_filter = 'all'
    query = (request.args.get('q') or '').strip()
    return render_template(
        'class_sessions.html',
        page=class_sessions_page_data(teacher_id, status_filter, query),
        tabs=SESSION_TABS, status_filter=status_filter, query=query,
        cs_dialog=class_session_dialog_data(teacher_id),
    )


# 獲取當前環境
@app.route('/api/environment')
def get_environment():
    return jsonify({
        'environment': ENVIRONMENT,
        'database_type': 'PostgreSQL' if ENVIRONMENT == 'production' else 'SQLite'
    })

# PDF 導出功能（使用前端渲染）
@app.route('/quiz-bank/<int:quiz_bank_id>/export-pdf')
@teacher_required
def export_quiz_bank_pdf(quiz_bank_id):
    quiz_bank = owned_or_404(QuizBank, quiz_bank_id)
    
    questions = Question.query.filter_by(quiz_bank_id=quiz_bank_id).order_by(Question.order_index).all()
    
    # 準備題目資料
    questions_data = []
    for q in questions:
        question_data = {
            'id': q.id,
            'title': q.title,
            'question_text': q.question_text,
            'question_type': q.question_type,
            'points': q.points
        }
        if q.question_data:
            question_data['data'] = json.loads(q.question_data)
        questions_data.append(question_data)
    
    # 渲染可列印的頁面（前端會用 html2pdf.js 生成 PDF）
    return render_template('quiz_pdf.html', 
                           quiz_bank=quiz_bank, 
                           questions=questions_data,
                           get_question_type_name=get_question_type_name)

def initialize_database():
    with app.app_context():
        db.create_all()
        ensure_schema_updates()

initialize_database()

if __name__ == '__main__':
    # 根據環境決定運行方式
    if ENVIRONMENT == 'development':
        app.run(debug=True, host='0.0.0.0', port=5000)
    # 生產環境下，由 Gunicorn 啟動應用，這裡不需要 app.run()
else:
    pass