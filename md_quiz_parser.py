import re

import yaml

SUPPORTED_TYPES = {'single_choice', 'multiple_choice', 'fill_blank', 'dropdown'}
TYPE_ALIASES = {
    'single': 'single_choice',
    'multiple': 'multiple_choice',
    'fill': 'fill_blank',
}


def _as_text(value):
    """Convert YAML scalar to stripped text; treat null as empty (not 'None')."""
    return '' if value is None else str(value).strip()


def _split_document(content):
    text = content.strip()
    if text.startswith('\ufeff'):
        text = text.lstrip('\ufeff')

    parts = re.split(r'^---\s*$', text, flags=re.MULTILINE)
    parts = [part.strip() for part in parts if part.strip()]
    if not parts:
        return None, []

    bank_meta = _parse_bank_meta(parts[0])
    question_blocks = _merge_question_parts(parts[1:])
    return bank_meta, question_blocks


def _parse_bank_meta(block):
    try:
        meta = yaml.safe_load(block) or {}
    except yaml.YAMLError:
        return None
    if isinstance(meta, dict) and 'title' in meta and 'type' not in meta:
        return meta
    return None


def _merge_question_parts(parts):
    blocks = []
    index = 0
    while index < len(parts):
        current = parts[index]
        if 'type:' in current and index + 1 < len(parts) and 'type:' not in parts[index + 1]:
            blocks.append(f'{current}\n\n{parts[index + 1]}')
            index += 2
        else:
            blocks.append(current)
            index += 1
    return blocks


_INDEX_PREFIX = re.compile(r'^(練習模式)?第 \d+ 題\s*')


def _reason(error):
    """Error text without the 「第 N 題」 prefix, for the preview row."""
    return _INDEX_PREFIX.sub('', error)


def _answer_text(question_type, question_data):
    if question_type == 'multiple_choice':
        return '、'.join(question_data.get('correct_answers') or [])
    return question_data.get('correct_answer', '') or ''


def _parse_question_block(index, block):
    """Return (question or None, errors, preview row or None)."""
    block = block.strip()
    if not block or block.startswith('#'):
        return None, [], None

    question, errors, row = _parse_question_meta(index, block)
    if row is not None:
        row['errors'] = [_reason(error) for error in errors]
    return question, errors, row


def _parse_question_meta(index, block):

    parts = block.split('\n\n')
    meta_text = parts[0].strip()
    remainder = '\n\n'.join(parts[1:]).strip() if len(parts) > 1 else ''

    body_text = remainder
    trailing_yaml = ''
    for marker in ('\noptions:', '\ncorrect_answers:', '\ncorrect_answer:'):
        if marker in remainder:
            split_at = remainder.find(marker)
            body_text = remainder[:split_at].strip()
            trailing_yaml = remainder[split_at + 1:].strip()
            break

    combined_meta = meta_text
    if trailing_yaml:
        combined_meta = f'{meta_text}\n{trailing_yaml}'

    try:
        meta = yaml.safe_load(combined_meta) or {}
    except yaml.YAMLError as exc:
        return None, [f'第 {index} 題 YAML 解析失敗：{exc}'], _empty_row(index)

    if not isinstance(meta, dict):
        return None, [f'第 {index} 題 metadata 格式錯誤'], _empty_row(index)

    if 'type' not in meta:
        return None, [], None

    question_type = TYPE_ALIASES.get(meta.get('type', ''), meta.get('type', ''))
    title = _as_text(meta.get('title'))
    question_text = body_text.strip()
    category = _as_text(meta.get('category'))

    errors = []
    raw_points = meta.get('points', 1)
    if raw_points is None or raw_points == '':
        raw_points = 1
    try:
        points = float(raw_points)
    except (TypeError, ValueError):
        points = 1
        errors.append(f'第 {index} 題 points 必須是數字')
    else:
        if points <= 0:
            errors.append(f'第 {index} 題 points 必須大於 0')

    if not title:
        errors.append(f'第 {index} 題缺少 title')
    if not question_text:
        errors.append(f'第 {index} 題缺少題目內容')
    if question_type not in SUPPORTED_TYPES:
        errors.append(f'第 {index} 題 type 不支援：{meta.get("type")}')

    question_data = _build_question_data(index, question_type, meta, errors)
    row = {
        'index': index,
        'title': title,
        'question_type': question_type,
        'category': category,
        'points': points,
        'answer': _answer_text(question_type, question_data),
    }
    if errors:
        return None, errors, row

    explanation = _as_text(meta.get('explanation'))
    if explanation:
        question_data['explanation'] = explanation

    return {
        'title': title,
        'question_text': question_text,
        'question_type': question_type,
        'points': points,
        'category': category,
        'question_data': question_data,
    }, [], row


def _empty_row(index):
    return {'index': index, 'title': '', 'question_type': '', 'category': '', 'points': None, 'answer': ''}


def _build_question_data(index, question_type, meta, errors):
    if question_type in ('single_choice', 'multiple_choice', 'dropdown'):
        options = meta.get('options') or []
        if not isinstance(options, list):
            errors.append(f'第 {index} 題 options 必須是列表')
            return {}
        options = [_as_text(opt) for opt in options]
        if any(not opt for opt in options):
            errors.append(f'第 {index} 題 options 含空值，特殊字元如 # 請加引號')
        if len(options) < 2:
            errors.append(f'第 {index} 題至少需要 2 個選項')

        if question_type == 'multiple_choice':
            correct_answers = meta.get('correct_answers') or []
            if not isinstance(correct_answers, list):
                errors.append(f'第 {index} 題沒有標記正確答案（correct_answers）')
                return {'options': options, 'correct_answers': []}
            correct_answers = [_as_text(ans) for ans in correct_answers]
            if any(not ans for ans in correct_answers):
                errors.append(f'第 {index} 題 correct_answers 含空值，特殊字元如 # 請加引號')
            if not any(ans for ans in correct_answers):
                errors.append(f'第 {index} 題沒有標記正確答案（correct_answers）')
            else:
                invalid = [ans for ans in correct_answers if ans and ans not in options]
                if invalid:
                    errors.append(f'第 {index} 題 correct_answers 不在 options 中')
            return {'options': options, 'correct_answers': correct_answers}

        correct_answer = _as_text(meta.get('correct_answer'))
        if not correct_answer:
            errors.append(f'第 {index} 題沒有標記正確答案（correct_answer）')
        elif correct_answer not in options:
            errors.append(f'第 {index} 題 correct_answer 不在 options 中')
        return {'options': options, 'correct_answer': correct_answer}

    if question_type == 'fill_blank':
        correct_answer = _as_text(meta.get('correct_answer'))
        if not correct_answer:
            errors.append(f'第 {index} 題沒有標記正確答案（correct_answer）')
        return {'correct_answer': correct_answer}

    return {}


def _parse_bank_settings(bank_meta):
    bank = {
        'title': str(bank_meta.get('title', '')).strip(),
        'description': str(bank_meta.get('description', '')).strip(),
        'quiz_mode': 'fixed',
        'session_question_count': None,
        'category_ratios': None,
    }

    mode = str(bank_meta.get('mode', 'fixed')).strip().lower()
    if mode == 'practice':
        bank['quiz_mode'] = 'practice'
        bank['session_question_count'] = int(bank_meta.get('session_question_count', 10) or 10)
        ratios = bank_meta.get('category_ratios') or {}
        if isinstance(ratios, dict):
            bank['category_ratios'] = {str(k).strip(): float(v) for k, v in ratios.items()}

    return bank


def _validate_rows_for_mode(rows, quiz_mode, errors):
    """A practice Quiz Bank draws by category, so each question needs one."""
    if quiz_mode != 'practice':
        return
    for row in rows:
        if row['question_type'] and not row['category']:
            error = f'練習模式第 {row["index"]} 題缺少 category'
            errors.append(error)
            row['errors'].append(_reason(error))


def _validate_bank(bank, questions, errors):
    if not bank.get('title'):
        errors.append('題庫缺少 title')
    if not questions:
        errors.append('至少需要 1 道題目')

    if bank.get('quiz_mode') == 'practice':
        from practice_utils import validate_category_ratios

        ratios = bank.get('category_ratios') or {}
        errors.extend(validate_category_ratios(ratios))


def _parse_question_blocks(question_blocks, errors, quiz_mode='fixed'):
    """Return (questions without problems, one preview row per question)."""
    questions = []
    rows = []
    for idx, block in enumerate(question_blocks, start=1):
        question, question_errors, row = _parse_question_block(idx, block)
        errors.extend(question_errors)
        if row is not None:
            rows.append(row)
        if question:
            questions.append(question)
    _validate_rows_for_mode(rows, quiz_mode, errors)
    return questions, rows


def parse_md_quiz(content):
    errors = []
    bank_meta, question_blocks = _split_document(content)

    if bank_meta is None and not question_blocks:
        error = ['檔案內容為空或格式錯誤']
        return {'bank': {}, 'questions': [], 'rows': [], 'errors': error, 'file_errors': error}

    bank_meta = bank_meta or {}
    bank = _parse_bank_settings(bank_meta)
    questions, rows = _parse_question_blocks(question_blocks, errors, bank['quiz_mode'])
    file_errors = []
    _validate_bank(bank, questions, file_errors)
    errors.extend(file_errors)

    return {
        'bank': bank,
        'questions': questions,
        'rows': rows,
        'errors': errors,
        'file_errors': file_errors,
    }


def parse_md_questions_append(content, quiz_mode='fixed', existing_categories=None):
    """解析要追加到既有題庫的 MD。

    支援：
    - 僅題目格式（無題庫 front matter）
    - 完整格式（有題庫 front matter，追加時忽略題庫設定）
    """
    errors = []
    warnings = []
    text = content.strip()
    if text.startswith('\ufeff'):
        text = text.lstrip('\ufeff')

    parts = re.split(r'^---\s*$', text, flags=re.MULTILINE)
    parts = [part.strip() for part in parts if part.strip()]
    if not parts:
        error = ['檔案內容為空或格式錯誤']
        return {'questions': [], 'rows': [], 'errors': error, 'file_errors': error, 'warnings': []}

    bank_meta = _parse_bank_meta(parts[0])
    if bank_meta is not None:
        # 完整格式：忽略題庫設定，只取題目
        question_parts = parts[1:]
    else:
        # 僅題目格式：全部視為題目區塊
        question_parts = parts

    question_blocks = _merge_question_parts(question_parts)
    questions, rows = _parse_question_blocks(question_blocks, errors, quiz_mode)

    file_errors = []
    if not questions and not errors:
        file_errors.append('至少需要 1 道題目')
    errors.extend(file_errors)

    existing = {
        str(category).strip()
        for category in (existing_categories or [])
        if str(category).strip()
    }
    if quiz_mode == 'practice':
        # Warn for any category not in current ratios, including when ratios are
        # still empty (otherwise new categories would be silently unusable).
        new_categories = sorted({
            q.get('category', '').strip()
            for q in questions
            if q.get('category', '').strip() and q.get('category', '').strip() not in existing
        })
        for category in new_categories:
            warnings.append(
                f'分類「{category}」不在目前比例設定中，題目會寫入但練習抽題不會抽到，請之後到管理頁調整比例'
            )

    return {
        'questions': questions,
        'rows': rows,
        'errors': errors,
        'file_errors': file_errors,
        'warnings': warnings,
    }
