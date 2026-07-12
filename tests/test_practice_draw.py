from types import SimpleNamespace

from practice_utils import (
    allocate_category_counts,
    draw_practice_questions,
    questions_in_id_order,
)


def _q(qid, category):
    return SimpleNamespace(id=qid, category=category)


def test_allocate_category_counts_sums_to_total():
    counts = allocate_category_counts(10, {'A': 50, 'B': 30, 'C': 20})
    assert sum(counts.values()) == 10


def test_draw_without_replacement_within_session():
    quiz_bank = SimpleNamespace(
        session_question_count=8,
        category_ratios='{"A": 50, "B": 50}',
    )
    questions = [_q(i, 'A') for i in range(1, 6)] + [_q(i, 'B') for i in range(6, 11)]
    selected, warnings = draw_practice_questions(quiz_bank, questions)
    assert len(selected) == 8
    assert len({q.id for q in selected}) == 8
    assert not any('可用題目不足' in w for w in warnings)


def test_draw_caps_when_pool_too_small():
    quiz_bank = SimpleNamespace(
        session_question_count=10,
        category_ratios='{"A": 100}',
    )
    questions = [_q(i, 'A') for i in range(1, 5)]
    selected, warnings = draw_practice_questions(quiz_bank, questions)
    assert len(selected) == 4
    assert len({q.id for q in selected}) == 4
    assert any('可用題目不足' in w for w in warnings)


def test_draw_redistributes_empty_category():
    quiz_bank = SimpleNamespace(
        session_question_count=6,
        category_ratios='{"A": 50, "B": 50}',
    )
    questions = [_q(i, 'A') for i in range(1, 10)]
    selected, warnings = draw_practice_questions(quiz_bank, questions)
    assert len(selected) == 6
    assert all(q.category == 'A' for q in selected)
    assert any('沒有題目' in w for w in warnings)


def test_questions_in_id_order():
    questions = [_q(3, 'A'), _q(1, 'A'), _q(2, 'A')]
    ordered = questions_in_id_order(questions, [1, 3, 2])
    assert [q.id for q in ordered] == [1, 3, 2]
