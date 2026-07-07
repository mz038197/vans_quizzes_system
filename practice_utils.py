import json
import random


def get_category_ratios(quiz_bank):
    if not quiz_bank.category_ratios:
        return {}
    try:
        return json.loads(quiz_bank.category_ratios)
    except (json.JSONDecodeError, TypeError):
        return {}


def allocate_category_counts(total, ratios):
    if not ratios or total <= 0:
        return {}

    categories = list(ratios.keys())
    raw = {cat: total * ratios[cat] / 100.0 for cat in categories}
    counts = {cat: int(raw[cat]) for cat in categories}
    remainder = total - sum(counts.values())

    fractions = sorted(categories, key=lambda c: raw[c] - counts[c], reverse=True)
    for i in range(remainder):
        counts[fractions[i % len(fractions)]] += 1

    return counts


def build_category_pools(questions):
    pools = {}
    for question in questions:
        category = (question.category or '').strip()
        pools.setdefault(category, []).append(question)
    return pools


def draw_practice_questions(quiz_bank, questions):
    ratios = get_category_ratios(quiz_bank)
    total = quiz_bank.session_question_count or 10

    if not ratios:
        return [], ['尚未設定分類比例']

    counts = allocate_category_counts(total, ratios)
    pools = build_category_pools(questions)
    warnings = []
    selected = []
    deficit = 0

    for category, count in counts.items():
        pool = pools.get(category, [])
        if not pool:
            deficit += count
            warnings.append(f'分類「{category}」沒有題目，{count} 題將分配給其他分類')
            continue
        selected.extend(random.choices(pool, k=count))

    if deficit > 0:
        available = [cat for cat in ratios if pools.get(cat)]
        if not available:
            return [], warnings + ['題庫中沒有任何符合分類的題目']
        extra_counts = allocate_category_counts(deficit, {cat: ratios[cat] for cat in available})
        for category, extra in extra_counts.items():
            pool = pools[category]
            selected.extend(random.choices(pool, k=extra))

    random.shuffle(selected)
    return selected, warnings


def serialize_question(question):
    data = {
        'id': question.id,
        'title': question.title,
        'question_text': question.question_text,
        'question_type': question.question_type,
        'points': question.points,
        'category': question.category or '',
    }
    if question.question_data:
        data.update(json.loads(question.question_data))
    return data


def validate_category_ratios(ratios):
    if not ratios:
        return ['請至少設定一個分類比例']
    if not isinstance(ratios, dict):
        return ['分類比例格式錯誤']

    errors = []
    total = 0
    for category, value in ratios.items():
        name = str(category).strip()
        if not name:
            errors.append('分類名稱不可為空')
            continue
        try:
            pct = float(value)
        except (TypeError, ValueError):
            errors.append(f'分類「{name}」的比例必須是數字')
            continue
        if pct <= 0:
            errors.append(f'分類「{name}」的比例必須大於 0')
        total += pct

    if abs(total - 100) > 0.01:
        errors.append(f'分類比例加總須為 100%，目前為 {total}%')
    return errors
