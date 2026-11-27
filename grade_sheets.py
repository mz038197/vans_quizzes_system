"""The 課堂總表 and the 課程總表 (spec #2 user stories 107-111, C11-C12; ticket 16 / #18).

Plain functions over plain data: app.py runs the queries and passes rows in.
A sheet has one row per trimmed student name and one column per (Class Session, Quiz Bank).
Each cell is the latest Take (highest Take number, grade_stats.take_numbers) and the number of Takes.
"""

import math

from grade_stats import HIGH_PERCENT, PASS_PERCENT, take_numbers, trimmed_name

NOT_ANSWERED = '未作答'


def whole_percent(value):
    """A percent as a whole number, half up (the screen and the CSV show the same number)."""
    return int(math.floor(value + 0.5))


def band(value):
    """Colour band of a percent: hi (HIGH_PERCENT and up), mid (PASS_PERCENT and up), lo (below)."""
    if value >= HIGH_PERCENT:
        return 'hi'
    return 'mid' if value >= PASS_PERCENT else 'lo'


def _mean(values):
    return sum(values) / len(values) if values else None


def build_sheet(columns, hand_ins):
    """`columns`: list of (class_session_id, quiz_bank_id) keys, in column order.
    `hand_ins`: iterable of dicts with id, name, class_session_id, quiz_bank_id, submitted_at, percent.
    Hand-ins outside the columns are left out.

    Returns {'columns': [{handed_in, average}], 'rows': [{name, cells, average, answered}]}.
    A cell is None (未作答) or {submission_id, quiz_bank_id, percent, takes}. Rows are sorted by name.
    """
    index = {key: i for i, key in enumerate(columns)}
    hand_ins = [h for h in hand_ins if (h['class_session_id'], h['quiz_bank_id']) in index]
    numbers = take_numbers((h['id'], h['name'], h['class_session_id'], h['quiz_bank_id'], h['submitted_at'])
                           for h in hand_ins)
    cells_by_name = {}
    for h in hand_ins:
        take, takes = numbers[h['id']]
        if take != takes:
            continue  # only the latest Take shows
        name = trimmed_name(h['name'])
        cells = cells_by_name.setdefault(name, [None] * len(columns))
        cells[index[(h['class_session_id'], h['quiz_bank_id'])]] = {
            'submission_id': h['id'], 'quiz_bank_id': h['quiz_bank_id'],
            'percent': h['percent'], 'takes': takes,
        }
    rows = []
    for name in sorted(cells_by_name):
        cells = cells_by_name[name]
        answered = [c['percent'] for c in cells if c]
        rows.append({'name': name, 'cells': cells, 'average': _mean(answered), 'answered': len(answered)})
    column_stats = []
    for i in range(len(columns)):
        values = [r['cells'][i]['percent'] for r in rows if r['cells'][i]]
        column_stats.append({'handed_in': len(values), 'average': _mean(values)})
    return {'columns': column_stats, 'rows': rows}


TAKES_SUFFIX = ' 次數'


def csv_header(column_titles):
    """Two CSV columns for each sheet column: the score, then its number of Takes."""
    return [h for title in column_titles for h in (title, title + TAKES_SUFFIX)]


def csv_cells(cell):
    """The two CSV values of one cell: the latest score as a plain number ('' when not answered)
    and the number of Takes, so a spreadsheet can calculate with the scores."""
    if cell is None:
        return ['', 0]
    return [whole_percent(cell['percent']), cell['takes']]
