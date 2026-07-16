from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import base64
import binascii
import json
import logging
import re
from datetime import datetime
import os
import sys
from md_quiz_parser import parse_md_quiz, parse_md_questions_append
from practice_utils import (
    draw_practice_questions,
    get_category_ratios,
    questions_in_id_order,
    serialize_question,
    validate_category_ratios,
)

logger = logging.getLogger(__name__)

# 環境設置
ENVIRONMENT = os.environ.get('FLASK_ENV', 'development')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# 根據環境選擇數據庫
if ENVIRONMENT == 'production':
    # 處理 render.com 中的 postgres:// 前綴問題
    database_url = os.environ.get('DATABASE_URL', '')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:  # development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz_platform.db'

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
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
CORS(app)

# 模板過濾器
@app.template_filter('from_json')
def from_json_filter(value):
    try:
        return json.loads(value) if value else {}
    except:
        return {}

@app.template_global()
def get_question_type_name(question_type):
    type_names = {
        'single_choice': '單選題',
        'multiple_choice': '多選題',
        'fill_blank': '填空題',
        'dropdown': '下拉選單',
        'dropdown_fillblank': '下拉選單填空題',
        'parsons': '程式碼排序題'
    }
    return type_names.get(question_type, question_type)

# 資料庫模型
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_teacher = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 關聯
    quiz_banks = db.relationship('QuizBank', backref='owner', lazy=True)

class QuizBank(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    access_code = db.Column(db.String(10), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    quiz_mode = db.Column(db.String(20), default='fixed')
    session_question_count = db.Column(db.Integer, default=10)
    category_ratios = db.Column(db.Text)
    scoring_mode = db.Column(db.String(20), default='explicit')  # explicit | average
    scoring_total_points = db.Column(db.Float, default=100)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # 關聯
    questions = db.relationship('Question', backref='quiz_bank', lazy=True, cascade='all, delete-orphan')
    submissions = db.relationship('Submission', backref='quiz_bank', lazy=True)

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
    session_question_ids = db.Column(db.Text)
    scoring_mode = db.Column(db.String(20))  # snapshot at submit time
    scoring_total_points = db.Column(db.Float)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    quiz_bank_id = db.Column(db.Integer, db.ForeignKey('quiz_bank.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_access_code():
    """生成6位數的存取代碼"""
    import random
    import string
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not QuizBank.query.filter_by(access_code=code).first():
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

def get_practice_session_key(access_code):
    return f'practice_session_{access_code}'

def create_quiz_bank_from_data(teacher_id, bank_data):
    quiz_bank = QuizBank(
        title=bank_data['title'],
        description=bank_data.get('description', ''),
        access_code=generate_access_code(),
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
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if User.query.filter_by(username=username).first():
            return jsonify({'error': '用戶名已存在'}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': '電子郵件已被使用'}), 400
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            is_teacher=True
        )
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'message': '註冊成功', 'redirect': '/login'})
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return jsonify({'message': '登入成功', 'redirect': '/teacher-dashboard'})
        
        return jsonify({'error': '用戶名或密碼錯誤'}), 401
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/teacher-dashboard')
@login_required
def teacher_dashboard():
    quiz_banks = QuizBank.query.filter_by(teacher_id=current_user.id).all()
    return render_template('teacher_dashboard.html', quiz_banks=quiz_banks)

@app.route('/create-quiz-bank', methods=['GET', 'POST'])
@login_required
def create_quiz_bank():
    if request.method == 'POST':
        data = request.get_json()
        title = data.get('title')
        description = data.get('description', '')
        
        quiz_bank = QuizBank(
            title=title,
            description=description,
            access_code=generate_access_code(),
            teacher_id=current_user.id
        )
        db.session.add(quiz_bank)
        db.session.commit()
        
        return jsonify({
            'message': '題庫建立成功',
            'quiz_bank_id': quiz_bank.id,
            'access_code': quiz_bank.access_code
        })
    
    return render_template('create_quiz_bank.html')

@app.route('/quiz-bank/<int:quiz_bank_id>')
@login_required
def manage_quiz_bank(quiz_bank_id):
    quiz_bank = QuizBank.query.get_or_404(quiz_bank_id)
    if quiz_bank.teacher_id != current_user.id:
        return redirect(url_for('teacher_dashboard'))

    questions = Question.query.filter_by(quiz_bank_id=quiz_bank_id).order_by(Question.order_index).all()
    category_stats = {}
    for question in questions:
        category = (question.category or '未分類').strip()
        category_stats[category] = category_stats.get(category, 0) + 1

    return render_template(
        'manage_quiz_bank.html',
        quiz_bank=quiz_bank,
        questions=questions,
        category_stats=category_stats,
        category_ratios=get_category_ratios(quiz_bank),
    )

@app.route('/quiz/<access_code>')
def take_quiz(access_code):
    quiz_bank = QuizBank.query.filter_by(access_code=access_code, is_active=True).first_or_404()

    if quiz_bank.quiz_mode == 'practice':
        return render_template(
            'practice_landing.html',
            quiz_bank=quiz_bank,
            category_ratios=get_category_ratios(quiz_bank),
        )

    questions = Question.query.filter_by(quiz_bank_id=quiz_bank.id).order_by(Question.order_index).all()
    scoring_mode, scoring_total = get_bank_scoring(quiz_bank)
    points_map = effective_points_map(questions, scoring_mode, scoring_total)
    questions_data = build_questions_data(questions, points_map)
    return render_template('take_quiz.html', quiz_bank=quiz_bank, questions=questions_data, is_practice=False)

@app.route('/quiz/<access_code>/play')
def play_quiz(access_code):
    quiz_bank = QuizBank.query.filter_by(access_code=access_code, is_active=True).first_or_404()
    session_key = get_practice_session_key(access_code)
    session_data = session.get(session_key)
    scoring_mode, scoring_total = get_bank_scoring(quiz_bank)

    if quiz_bank.quiz_mode == 'practice':
        if not session_data or not session_data.get('question_ids'):
            return redirect(url_for('take_quiz', access_code=access_code))

        loaded = Question.query.filter(Question.id.in_(session_data['question_ids'])).all()
        questions = questions_in_id_order(loaded, session_data['question_ids'])
        points_map = effective_points_map(questions, scoring_mode, scoring_total)
        questions_data = build_questions_data(questions, points_map)
        return render_template(
            'take_quiz.html',
            quiz_bank=quiz_bank,
            questions=questions_data,
            is_practice=True,
            draw_warnings=session_data.get('warnings', []),
        )

    questions = Question.query.filter_by(quiz_bank_id=quiz_bank.id).order_by(Question.order_index).all()
    points_map = effective_points_map(questions, scoring_mode, scoring_total)
    questions_data = build_questions_data(questions, points_map)
    return render_template('take_quiz.html', quiz_bank=quiz_bank, questions=questions_data, is_practice=False)

# API 路由
@app.route('/api/quiz-bank/<int:quiz_bank_id>/toggle', methods=['POST'])
@login_required
def toggle_quiz_bank(quiz_bank_id):
    quiz_bank = QuizBank.query.get_or_404(quiz_bank_id)
    if quiz_bank.teacher_id != current_user.id:
        return jsonify({'error': '無權限操作'}), 403
    
    quiz_bank.is_active = not quiz_bank.is_active
    db.session.commit()
    
    return jsonify({'message': '操作成功', 'is_active': quiz_bank.is_active})

@app.route('/api/quiz-bank/<int:quiz_bank_id>', methods=['DELETE'])
@login_required
def delete_quiz_bank(quiz_bank_id):
    quiz_bank = QuizBank.query.get_or_404(quiz_bank_id)
    if quiz_bank.teacher_id != current_user.id:
        return jsonify({'error': '無權限操作'}), 403
    
    try:
        db.session.delete(quiz_bank)
        db.session.commit()
        return jsonify({'message': '題庫已成功刪除'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '刪除失敗，請稍後再試'}), 500

@app.route('/api/quiz-bank/<int:quiz_bank_id>/questions', methods=['GET', 'POST'])
@login_required
def manage_questions(quiz_bank_id):
    quiz_bank = QuizBank.query.get_or_404(quiz_bank_id)
    if quiz_bank.teacher_id != current_user.id:
        return jsonify({'error': '無權限操作'}), 403
    
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
@login_required
def manage_question(question_id):
    question = Question.query.get_or_404(question_id)
    quiz_bank = question.quiz_bank
    
    if quiz_bank.teacher_id != current_user.id:
        return jsonify({'error': '無權限操作'}), 403
    
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

@app.route('/api/quiz-bank/<int:quiz_bank_id>/practice-config', methods=['PUT'])
@login_required
def update_practice_config(quiz_bank_id):
    quiz_bank = QuizBank.query.get_or_404(quiz_bank_id)
    if quiz_bank.teacher_id != current_user.id:
        return jsonify({'error': '無權限操作'}), 403

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

@app.route('/api/quiz/<access_code>/draw', methods=['POST'])
def draw_practice_quiz(access_code):
    quiz_bank = QuizBank.query.filter_by(access_code=access_code, is_active=True).first_or_404()
    if quiz_bank.quiz_mode != 'practice':
        return jsonify({'error': '此題庫不是練習模式'}), 400

    all_questions = Question.query.filter_by(quiz_bank_id=quiz_bank.id).all()
    selected, warnings = draw_practice_questions(quiz_bank, all_questions)
    if not selected:
        return jsonify({'error': warnings[0] if warnings else '無法抽題', 'warnings': warnings}), 400

    question_ids = [q.id for q in selected]
    session[get_practice_session_key(access_code)] = {
        'question_ids': question_ids,
        'warnings': warnings,
    }

    return jsonify({
        'message': '抽題成功',
        'question_count': len(question_ids),
        'warnings': warnings,
        'redirect': url_for('play_quiz', access_code=access_code),
    })

@app.route('/api/import-quiz-md/preview', methods=['POST'])
@login_required
def preview_import_quiz_md():
    try:
        uploaded = request.files.get('file')
        if not uploaded or not uploaded.filename:
            return jsonify({'success': False, 'errors': ['請上傳 .md 檔案']}), 400

        content = uploaded.read().decode('utf-8-sig')
        parsed = parse_md_quiz(content)
    except Exception as exc:
        return jsonify({'success': False, 'errors': [f'解析失敗：{exc}']}), 500
    if parsed['errors']:
        return jsonify({'success': False, 'errors': parsed['errors']}), 400

    preview_questions = []
    for index, question in enumerate(parsed['questions'], start=1):
        preview_questions.append({
            'index': index,
            'title': question['title'],
            'question_type': question['question_type'],
            'category': question.get('category', ''),
            'points': question.get('points', 1),
        })

    return jsonify({
        'success': True,
        'bank': parsed['bank'],
        'questions': preview_questions,
        'question_count': len(preview_questions),
    })

@app.route('/api/import-quiz-md/confirm', methods=['POST'])
@login_required
def confirm_import_quiz_md():
    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename:
        return jsonify({'success': False, 'errors': ['請上傳 .md 檔案']}), 400

    content = uploaded.read().decode('utf-8-sig')
    parsed = parse_md_quiz(content)
    if parsed['errors']:
        return jsonify({'success': False, 'errors': parsed['errors']}), 400

    try:
        quiz_bank = create_quiz_bank_from_data(current_user.id, parsed['bank'])
        create_questions_for_bank(quiz_bank.id, parsed['questions'])
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'errors': ['匯入失敗，請稍後再試']}), 500

    return jsonify({
        'success': True,
        'message': '題庫匯入成功',
        'quiz_bank_id': quiz_bank.id,
        'access_code': quiz_bank.access_code,
        'question_count': len(parsed['questions']),
    })

@app.route('/api/import-quiz-md/template')
@login_required
def download_import_template():
    return send_from_directory('static/templates', 'quiz_template.md', as_attachment=True)

@app.route('/api/quiz-bank/import-md/questions-template')
@login_required
def download_append_questions_template():
    return send_from_directory('static/templates', 'quiz_questions_append.md', as_attachment=True)

def _build_append_preview(questions):
    preview_questions = []
    for index, question in enumerate(questions, start=1):
        preview_questions.append({
            'index': index,
            'title': question['title'],
            'question_type': question['question_type'],
            'category': question.get('category', ''),
            'points': question.get('points', 1),
        })
    return preview_questions

@app.route('/api/quiz-bank/<int:quiz_bank_id>/import-md/preview', methods=['POST'])
@login_required
def preview_append_quiz_md(quiz_bank_id):
    quiz_bank = QuizBank.query.get_or_404(quiz_bank_id)
    if quiz_bank.teacher_id != current_user.id:
        return jsonify({'success': False, 'errors': ['無權限操作']}), 403

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
        return jsonify({'success': False, 'errors': parsed['errors'], 'warnings': parsed.get('warnings', [])}), 400

    return jsonify({
        'success': True,
        'questions': _build_append_preview(parsed['questions']),
        'question_count': len(parsed['questions']),
        'warnings': parsed.get('warnings', []),
    })

@app.route('/api/quiz-bank/<int:quiz_bank_id>/import-md/confirm', methods=['POST'])
@login_required
def confirm_append_quiz_md(quiz_bank_id):
    quiz_bank = QuizBank.query.get_or_404(quiz_bank_id)
    if quiz_bank.teacher_id != current_user.id:
        return jsonify({'success': False, 'errors': ['無權限操作']}), 403

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

@app.route('/api/quiz/<access_code>/submit', methods=['POST'])
def submit_quiz(access_code):
    quiz_bank = QuizBank.query.filter_by(access_code=access_code, is_active=True).first_or_404()
    data = request.get_json()

    student_name = data.get('student_name')
    student_email = data.get('student_email', '')
    answers = data.get('answers', {})

    if not student_name:
        return jsonify({'error': '請輸入姓名'}), 400

    is_practice = quiz_bank.quiz_mode == 'practice'
    session_key = get_practice_session_key(access_code)
    session_data = session.get(session_key) if is_practice else None

    if is_practice:
        if not session_data or not session_data.get('question_ids'):
            return jsonify({'error': '練習場次已失效，請重新開始練習'}), 400
        loaded = Question.query.filter(Question.id.in_(session_data['question_ids'])).all()
        questions = questions_in_id_order(loaded, session_data['question_ids'])
    else:
        questions = Question.query.filter_by(quiz_bank_id=quiz_bank.id).order_by(Question.order_index).all()

    scoring_mode, scoring_total = get_bank_scoring(quiz_bank)
    points_map = effective_points_map(questions, scoring_mode, scoring_total)
    total_points = sum(points_map.values()) if points_map else 0
    score = 0
    for question in questions:
        user_answer = answers.get(str(question.id))
        score += grade_question(question, user_answer, points=points_map.get(question.id))

    submission = Submission(
        student_name=student_name,
        student_email=student_email,
        answers=json.dumps(answers),
        score=score,
        total_points=total_points,
        quiz_bank_id=quiz_bank.id,
        is_practice=is_practice,
        session_question_ids=json.dumps([q.id for q in questions]) if is_practice else None,
        scoring_mode=scoring_mode,
        scoring_total_points=scoring_total,
    )

    db.session.add(submission)
    db.session.commit()

    if is_practice:
        session.pop(session_key, None)

    return jsonify({
        'message': '測驗提交成功',
        'score': score,
        'total_points': total_points,
        'percentage': round((score / total_points * 100) if total_points > 0 else 0, 2),
        'submission_id': submission.id,
        'is_practice': is_practice,
        'retry_url': url_for('take_quiz', access_code=access_code) if is_practice else None,
    })

@app.route('/result/<int:submission_id>')
def view_result(submission_id):
    submission = Submission.query.get_or_404(submission_id)

    if submission.session_question_ids:
        question_ids = json.loads(submission.session_question_ids)
        loaded = Question.query.filter(Question.id.in_(question_ids)).all()
        questions = questions_in_id_order(loaded, question_ids)
    else:
        questions = Question.query.filter_by(quiz_bank_id=submission.quiz_bank_id).order_by(Question.order_index).all()

    student_answers = json.loads(submission.answers) if submission.answers else {}
    snap_mode = getattr(submission, 'scoring_mode', None) or 'explicit'
    snap_total = getattr(submission, 'scoring_total_points', None)
    if snap_total is None:
        # Legacy rows: prefer the attempt's stored total over a hardcoded 100.
        # Use explicit None check so a legitimate 0 total is preserved.
        snap_total = submission.total_points if submission.total_points is not None else 100
    question_points = effective_points_map(questions, snap_mode, snap_total)
    return render_template(
        'result.html',
        submission=submission,
        questions=questions,
        student_answers=student_answers,
        question_points=question_points,
    )

@app.route('/quiz-bank/<int:quiz_bank_id>/submissions')
@login_required
def view_submissions_page(quiz_bank_id):
    quiz_bank = QuizBank.query.get_or_404(quiz_bank_id)
    if quiz_bank.teacher_id != current_user.id:
        return redirect(url_for('teacher_dashboard'))
    
    return render_template('submissions.html', quiz_bank=quiz_bank)

@app.route('/api/quiz-bank/<int:quiz_bank_id>/submissions')
@login_required
def view_submissions(quiz_bank_id):
    quiz_bank = QuizBank.query.get_or_404(quiz_bank_id)
    if quiz_bank.teacher_id != current_user.id:
        return jsonify({'error': '無權限查看'}), 403
    
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
            'submitted_at': s.submitted_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_practice': bool(s.is_practice),
        })
    
    return jsonify(submissions_data)

@app.route('/api/submission/<int:submission_id>', methods=['DELETE'])
@login_required
def delete_submission(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    quiz_bank = submission.quiz_bank
    
    if quiz_bank.teacher_id != current_user.id:
        return jsonify({'error': '無權限操作'}), 403
    
    try:
        db.session.delete(submission)
        db.session.commit()
        return jsonify({'message': '成績已成功刪除'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '刪除失敗，請稍後再試'}), 500

# 獲取當前環境
@app.route('/api/environment')
def get_environment():
    return jsonify({
        'environment': ENVIRONMENT,
        'database_type': 'PostgreSQL' if ENVIRONMENT == 'production' else 'SQLite'
    })

# PDF 導出功能（使用前端渲染）
@app.route('/quiz-bank/<int:quiz_bank_id>/export-pdf')
@login_required
def export_quiz_bank_pdf(quiz_bank_id):
    quiz_bank = QuizBank.query.get_or_404(quiz_bank_id)
    if quiz_bank.teacher_id != current_user.id:
        return redirect(url_for('teacher_dashboard'))
    
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