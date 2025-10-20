from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import json
import uuid
from datetime import datetime
import os
import sys

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
    points = db.Column(db.Integer, default=1)
    order_index = db.Column(db.Integer, default=0)
    quiz_bank_id = db.Column(db.Integer, db.ForeignKey('quiz_bank.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(100), nullable=False)
    student_email = db.Column(db.String(120))
    answers = db.Column(db.Text)  # JSON格式儲存答案
    score = db.Column(db.Float, default=0)
    total_points = db.Column(db.Integer, default=0)
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
    return render_template('manage_quiz_bank.html', quiz_bank=quiz_bank, questions=questions)

@app.route('/quiz/<access_code>')
def take_quiz(access_code):
    quiz_bank = QuizBank.query.filter_by(access_code=access_code, is_active=True).first_or_404()
    questions = Question.query.filter_by(quiz_bank_id=quiz_bank.id).order_by(Question.order_index).all()
    
    # 準備題目資料，解析JSON格式的question_data
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
            question_data.update(json.loads(q.question_data))
        questions_data.append(question_data)
    
    return render_template('take_quiz.html', quiz_bank=quiz_bank, questions=questions_data)

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
                'order_index': q.order_index
            }
            if q.question_data:
                question_data['question_data'] = json.loads(q.question_data)
            questions_data.append(question_data)
        return jsonify(questions_data)
    
    elif request.method == 'POST':
        data = request.get_json()
        
        # 獲取最大的order_index
        max_order = db.session.query(db.func.max(Question.order_index)).filter_by(quiz_bank_id=quiz_bank_id).scalar() or 0
        
        question = Question(
            title=data.get('title'),
            question_text=data.get('question_text'),
            question_type=data.get('question_type'),
            question_data=json.dumps(data.get('question_data', {})),
            points=data.get('points', 1),
            order_index=max_order + 1,
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
        data = request.get_json()
        question.title = data.get('title', question.title)
        question.question_text = data.get('question_text', question.question_text)
        question.question_type = data.get('question_type', question.question_type)
        question.question_data = json.dumps(data.get('question_data', {}))
        question.points = data.get('points', question.points)
        
        db.session.commit()
        return jsonify({'message': '題目更新成功'})
    
    elif request.method == 'DELETE':
        db.session.delete(question)
        db.session.commit()
        return jsonify({'message': '題目刪除成功'})

@app.route('/api/quiz/<access_code>/submit', methods=['POST'])
def submit_quiz(access_code):
    quiz_bank = QuizBank.query.filter_by(access_code=access_code, is_active=True).first_or_404()
    data = request.get_json()
    
    student_name = data.get('student_name')
    student_email = data.get('student_email', '')
    answers = data.get('answers', {})
    
    if not student_name:
        return jsonify({'error': '請輸入姓名'}), 400
    
    # 計算分數
    questions = Question.query.filter_by(quiz_bank_id=quiz_bank.id).all()
    total_points = sum(q.points for q in questions)
    score = 0
    
    for question in questions:
        question_data = json.loads(question.question_data) if question.question_data else {}
        user_answer = answers.get(str(question.id))
        
        if question.question_type in ['single_choice', 'dropdown']:
            correct_answer = question_data.get('correct_answer')
            
            # 調試信息
            # 注意：LaTeX 語法會保留在原始文本中進行比對，確保數學公式的準確性
            print(f"Question {question.id} ({question.question_type}): {question.title}")
            print(f"  User answer: {repr(user_answer)} (type: {type(user_answer)})")
            print(f"  Correct answer: {repr(correct_answer)} (type: {type(correct_answer)})")
            
            # 特殊處理：檢查是否是JSON轉義問題
            if user_answer and correct_answer:
                print(f"  User answer length: {len(str(user_answer))}")
                print(f"  Correct answer length: {len(str(correct_answer))}")
                print(f"  User answer first 100 chars: {repr(str(user_answer)[:100])}")
                print(f"  Correct answer first 100 chars: {repr(str(correct_answer)[:100])}")
            
            # 多行文本比較策略
            is_correct = False
            comparison_method = ""
            
            # 1. 直接比較
            if user_answer == correct_answer:
                is_correct = True
                comparison_method = "exact_match"
            
            # 2. 字符串化後比較
            elif str(user_answer) == str(correct_answer):
                is_correct = True
                comparison_method = "string_match"
            
            # 3. 標準化比較（去除前後空白）
            elif str(user_answer).strip() == str(correct_answer).strip():
                is_correct = True
                comparison_method = "normalized_match"
            
            # 4. 換行符標準化比較
            else:
                import re
                # 統一換行符為 \n
                user_normalized = str(user_answer).replace('\r\n', '\n').replace('\r', '\n').strip() if user_answer else ""
                correct_normalized = str(correct_answer).replace('\r\n', '\n').replace('\r', '\n').strip() if correct_answer else ""
                
                if user_normalized == correct_normalized:
                    is_correct = True
                    comparison_method = "newline_normalized_match"
                
                # 5. 深度清理比較（保持行結構但標準化空白）
                elif not is_correct:
                    # 分行處理，每行內部標準化空白，但保持行結構
                    def normalize_multiline_code(text):
                        if not text:
                            return ""
                        print(f"    Normalizing: {repr(text[:100])}")
                        # 統一換行符
                        text = text.replace('\r\n', '\n').replace('\r', '\n')
                        lines = text.split('\n')
                        normalized_lines = []
                        for i, line in enumerate(lines):
                            # 保持行首縮排，但標準化其他空白
                            stripped = line.rstrip()  # 去除行尾空白
                            if stripped:
                                # 計算行首空白
                                leading_spaces = len(line) - len(line.lstrip())
                                # 將制表符轉換為4個空格
                                content = line.lstrip().replace('\t', '    ')
                                # 標準化內容中的多餘空白
                                content = re.sub(r' +', ' ', content)
                                normalized_lines.append(' ' * leading_spaces + content)
                                print(f"    Line {i}: {repr(line)} -> {repr(' ' * leading_spaces + content)}")
                            else:
                                normalized_lines.append('')
                                print(f"    Line {i}: empty")
                        result = '\n'.join(normalized_lines).strip()
                        print(f"    Result: {repr(result[:100])}")
                        return result
                    
                    user_multiline_clean = normalize_multiline_code(user_answer)
                    correct_multiline_clean = normalize_multiline_code(correct_answer)
                    
                    if user_multiline_clean == correct_multiline_clean:
                        is_correct = True
                        comparison_method = "multiline_normalized_match"
                    
                    # 6. 最後的降級比較（完全忽略空白結構）
                    elif not is_correct:
                        # 移除所有空白字符後比較
                        user_no_whitespace = re.sub(r'\s+', '', str(user_answer)) if user_answer else ""
                        correct_no_whitespace = re.sub(r'\s+', '', str(correct_answer)) if correct_answer else ""
                        
                        print(f"  Whitespace removed comparison:")
                        print(f"    User: {repr(user_no_whitespace[:50])}")
                        print(f"    Correct: {repr(correct_no_whitespace[:50])}")
                        
                        if user_no_whitespace == correct_no_whitespace:
                            is_correct = True
                            comparison_method = "whitespace_ignored_match"
                        
                        # 7. 終極比較：處理可能的JSON轉義問題
                        elif not is_correct:
                            try:
                                # 嘗試解碼可能的JSON轉義
                                import json as json_module
                                user_decoded = user_answer
                                correct_decoded = correct_answer
                                
                                # 如果看起來像JSON字符串，嘗試解碼
                                if isinstance(user_answer, str) and (user_answer.startswith('"') or '\\n' in user_answer):
                                    try:
                                        user_decoded = json_module.loads('"' + user_answer.replace('"', '\\"') + '"')
                                    except:
                                        pass
                                
                                if isinstance(correct_answer, str) and (correct_answer.startswith('"') or '\\n' in correct_answer):
                                    try:
                                        correct_decoded = json_module.loads('"' + correct_answer.replace('"', '\\"') + '"')
                                    except:
                                        pass
                                
                                print(f"  JSON decode attempt:")
                                print(f"    User decoded: {repr(user_decoded[:50])}")
                                print(f"    Correct decoded: {repr(correct_decoded[:50])}")
                                
                                if user_decoded == correct_decoded:
                                    is_correct = True
                                    comparison_method = "json_decoded_match"
                                
                            except Exception as e:
                                print(f"  JSON decode error: {e}")
            
            print(f"  Match result: {is_correct} (method: {comparison_method})")
            
            if is_correct:
                score += question.points
                print(f"  ✓ Correct! Points added: {question.points}")
            else:
                print(f"  ✗ Incorrect!")
                # 詳細錯誤分析
                if user_answer and correct_answer:
                    print(f"  User length: {len(str(user_answer))}, Correct length: {len(str(correct_answer))}")
                    
                    # 顯示前50個字符的差異
                    user_str = str(user_answer)
                    correct_str = str(correct_answer)
                    max_check = min(50, max(len(user_str), len(correct_str)))
                    
                    for i in range(max_check):
                        u_char = user_str[i] if i < len(user_str) else '(end)'
                        c_char = correct_str[i] if i < len(correct_str) else '(end)'
                        
                        if u_char != c_char:
                            print(f"  First diff at pos {i}: user='{u_char}' (ord {ord(u_char) if u_char != '(end)' else 'N/A'}), correct='{c_char}' (ord {ord(c_char) if c_char != '(end)' else 'N/A'})")
                            break
                
        elif question.question_type == 'dropdown_fillblank':
            # 下拉選單填空題評分
            blanks_data = question_data.get('blanks', [])
            user_answers = user_answer if isinstance(user_answer, dict) else {}
            
            # 檢查所有空格是否都回答正確
            all_correct = True
            for i, blank in enumerate(blanks_data):
                blank_id = f"blank_{i}"
                correct_answer = blank.get('correct_answer')
                user_blank_answer = user_answers.get(blank_id)
                if user_blank_answer != correct_answer:
                    all_correct = False
                    break
            
            if all_correct and len(user_answers) == len(blanks_data):
                score += question.points
                
        elif question.question_type == 'multiple_choice':
            correct_answers = set(question_data.get('correct_answers', []))
            user_answers = set(user_answer if isinstance(user_answer, list) else [])
            if user_answers == correct_answers:
                score += question.points
                
        elif question.question_type == 'fill_blank':
            # 填空題比對：LaTeX 語法會被保留並比對，確保數學公式準確性
            correct_answer = question_data.get('correct_answer', '').lower().strip()
            user_answer_clean = (user_answer or '').lower().strip()
            if user_answer_clean == correct_answer:
                score += question.points
                
        elif question.question_type == 'parsons':
            # 處理程式排序題
            print(f"Question {question.id} - Parsons type")
            print(f"  Question data: {question_data}")
            print(f"  User answer: {user_answer}")
            
            # 新格式：使用slot_answers比對
            if 'slot_answers' in question_data and isinstance(user_answer, dict) and 'slot_answers' in user_answer:
                correct_slot_answers = question_data.get('slot_answers', {})
                user_slot_answers = user_answer.get('slot_answers', {})
                
                print(f"  New format - Correct slot answers: {correct_slot_answers}")
                print(f"  New format - User slot answers: {user_slot_answers}")
                
                # 比較每個空格的答案是否正確
                all_correct = True
                for slot_num, correct_label in correct_slot_answers.items():
                    user_label = user_slot_answers.get(str(slot_num))
                    print(f"    Slot {slot_num}: user={user_label}, correct={correct_label}")
                    if user_label != correct_label:
                        all_correct = False
                        break
                
                if all_correct and len(user_slot_answers) == len(correct_slot_answers):
                    score += question.points
                    print(f"  ✓ Correct! Points added: {question.points}")
                else:
                    print(f"  ✗ Incorrect!")
            
            # 舊格式兼容：使用correct_order比對
            elif 'correct_order' in question_data:
                correct_order = question_data.get('correct_order', [])
                
                # 檢查答案格式並提取答案
                user_order = []
                
                # 新的複合格式 {order: [...], slots: {...}}
                if isinstance(user_answer, dict) and 'order' in user_answer:
                    user_order = user_answer['order'] if isinstance(user_answer['order'], list) else []
                
                # 字典格式 {1: "code1", 2: "code2", ...}
                elif isinstance(user_answer, dict) and 'slot_answers' in user_answer:
                    # 從slot_answers提取順序
                    slot_answers = user_answer['slot_answers']
                    sorted_slots = sorted([int(k) for k in slot_answers.keys()])
                    user_order = [slot_answers[str(slot)] for slot in sorted_slots]
                
                # 舊的字典格式 {1: "code1", 2: "code2", ...}
                elif isinstance(user_answer, dict):
                    # 將字典轉換為列表
                    for i in range(1, len(correct_order) + 1):
                        if str(i) in user_answer:
                            user_order.append(user_answer[str(i)])
                        elif i in user_answer:
                            user_order.append(user_answer[i])
                
                # 列表格式 ["code1", "code2", ...]
                elif isinstance(user_answer, list):
                    user_order = user_answer
                
                print(f"  Old format - User order: {user_order}")
                print(f"  Old format - Correct order: {correct_order}")
                
                # 比較順序是否正確
                if len(user_order) == len(correct_order) and all(a == b for a, b in zip(user_order, correct_order)):
                    score += question.points
                    print(f"  ✓ Correct! Points added: {question.points}")
                else:
                    print(f"  ✗ Incorrect!")
    
    # 儲存結果
    submission = Submission(
        student_name=student_name,
        student_email=student_email,
        answers=json.dumps(answers),
        score=score,
        total_points=total_points,
        quiz_bank_id=quiz_bank.id
    )
    
    db.session.add(submission)
    db.session.commit()
    
    return jsonify({
        'message': '測驗提交成功',
        'score': score,
        'total_points': total_points,
        'percentage': round((score / total_points * 100) if total_points > 0 else 0, 2),
        'submission_id': submission.id
    })

@app.route('/result/<int:submission_id>')
def view_result(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    
    # 獲取題目和答案詳情
    questions = Question.query.filter_by(quiz_bank_id=submission.quiz_bank_id).order_by(Question.order_index).all()
    
    # 解析學生答案
    student_answers = json.loads(submission.answers) if submission.answers else {}
    
    return render_template('result.html', submission=submission, questions=questions, student_answers=student_answers)

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
            'submitted_at': s.submitted_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    return jsonify(submissions_data)

# 獲取當前環境
@app.route('/api/environment')
def get_environment():
    return jsonify({
        'environment': ENVIRONMENT,
        'database_type': 'PostgreSQL' if ENVIRONMENT == 'production' else 'SQLite'
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    # 根據環境決定運行方式
    if ENVIRONMENT == 'development':
        app.run(debug=True, host='0.0.0.0', port=5000)
    # 生產環境下，由 Gunicorn 啟動應用，這裡不需要 app.run()
else:
    # 只在設置了特定環境變量時初始化數據庫
    should_init_db = os.environ.get('INIT_DB', 'false').lower() == 'true'
    if should_init_db:
        with app.app_context():
            db.create_all()
            print("數據庫初始化完成")