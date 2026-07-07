import re

import yaml

SUPPORTED_TYPES = {'single_choice', 'multiple_choice', 'fill_blank', 'dropdown'}
TYPE_ALIASES = {
    'single': 'single_choice',
    'multiple': 'multiple_choice',
    'fill': 'fill_blank',
}


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


def _parse_question_block(index, block):
    block = block.strip()
    if not block or block.startswith('#'):
        return None, []

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
        return None, [f'第 {index} 題 YAML 解析失敗：{exc}']

    if not isinstance(meta, dict):
        return None, [f'第 {index} 題 metadata 格式錯誤']

    if 'type' not in meta:
        return None, []

    question_type = TYPE_ALIASES.get(meta.get('type', ''), meta.get('type', ''))
    title = str(meta.get('title', '')).strip()
    question_text = body_text.strip()
    category = str(meta.get('category', '')).strip()
    points = int(meta.get('points', 1) or 1)

    errors = []
    if not title:
        errors.append(f'第 {index} 題缺少 title')
    if not question_text:
        errors.append(f'第 {index} 題缺少題目內容')
    if question_type not in SUPPORTED_TYPES:
        errors.append(f'第 {index} 題 type 不支援：{meta.get("type")}')

    question_data = _build_question_data(index, question_type, meta, errors)
    if errors:
        return None, errors

    return {
        'title': title,
        'question_text': question_text,
        'question_type': question_type,
        'points': points,
        'category': category,
        'question_data': question_data,
    }, []


def _build_question_data(index, question_type, meta, errors):
    if question_type in ('single_choice', 'multiple_choice', 'dropdown'):
        options = meta.get('options') or []
        if not isinstance(options, list):
            errors.append(f'第 {index} 題 options 必須是列表')
            return {}
        options = [str(opt) for opt in options]
        if len(options) < 2:
            errors.append(f'第 {index} 題至少需要 2 個選項')

        if question_type == 'multiple_choice':
            correct_answers = meta.get('correct_answers') or []
            if not isinstance(correct_answers, list) or not correct_answers:
                errors.append(f'第 {index} 題缺少 correct_answers')
            else:
                correct_answers = [str(ans) for ans in correct_answers]
                invalid = [ans for ans in correct_answers if ans not in options]
                if invalid:
                    errors.append(f'第 {index} 題 correct_answers 不在 options 中')
            return {'options': options, 'correct_answers': correct_answers}

        correct_answer = str(meta.get('correct_answer', '')).strip()
        if not correct_answer:
            errors.append(f'第 {index} 題缺少 correct_answer')
        elif correct_answer not in options:
            errors.append(f'第 {index} 題 correct_answer 不在 options 中')
        return {'options': options, 'correct_answer': correct_answer}

    if question_type == 'fill_blank':
        correct_answer = str(meta.get('correct_answer', '')).strip()
        if not correct_answer:
            errors.append(f'第 {index} 題缺少 correct_answer')
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


def _validate_bank(bank, questions, errors):
    if not bank.get('title'):
        errors.append('題庫缺少 title')
    if not questions:
        errors.append('至少需要 1 道題目')

    if bank.get('quiz_mode') == 'practice':
        from practice_utils import validate_category_ratios

        ratios = bank.get('category_ratios') or {}
        errors.extend(validate_category_ratios(ratios))
        for idx, question in enumerate(questions, start=1):
            if not question.get('category'):
                errors.append(f'練習模式第 {idx} 題缺少 category')


def parse_md_quiz(content):
    errors = []
    bank_meta, question_blocks = _split_document(content)

    if bank_meta is None and not question_blocks:
        return {'bank': {}, 'questions': [], 'errors': ['檔案內容為空或格式錯誤']}

    bank_meta = bank_meta or {}
    bank = _parse_bank_settings(bank_meta)

    questions = []
    for idx, block in enumerate(question_blocks, start=1):
        question, question_errors = _parse_question_block(idx, block)
        errors.extend(question_errors)
        if question:
            questions.append(question)

    _validate_bank(bank, questions, errors)

    return {
        'bank': bank,
        'questions': questions,
        'errors': errors,
    }
