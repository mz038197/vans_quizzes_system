"""A short summary of the Quiz Banks a Class Session offers, for the 儀表板 card and the 課堂 page.

With one or two Quiz Banks the pages list them in full. With more, they show one summary line and
open the details on demand. The details name what every Quiz Bank shares only once: the start of
the titles, the Time Limit, the Folder; each Quiz Bank keeps only what is its own.
"""

FULL_LIST_UP_TO = 2
_BREAKS = ' （(·-–—:：|｜/'
_BRACKETS = {'（': '）', '(': ')'}


def time_limit_text(minutes, short=False):
    if not minutes:
        return '不限時'
    return f'{minutes} 分' if short else f'時限 {minutes} 分鐘'


def _shared_start(titles):
    """The start that every title shares, cut back to a word break, or '' when there is none.
    Every title must keep a part of its own after it."""
    if len(titles) < 2:
        return ''
    first = titles[0]
    end = 0
    while end < len(first) and all(len(t) > end and t[end] == first[end] for t in titles):
        end += 1
    while end > 0 and not (first[end] in _BREAKS if end < len(first) else False):
        end -= 1
    end = _before_open_bracket(first, end)
    shared = first[:end].rstrip(_BREAKS)
    if len(shared) < 2 or any(not t[end:].strip(_BREAKS) for t in titles):
        return ''
    return shared


def _before_open_bracket(text, end):
    """Cut `end` back so that text[:end] leaves no bracket open."""
    opened = []
    for i, ch in enumerate(text[:end]):
        if ch in _BRACKETS:
            opened.append(i)
        elif opened and ch == _BRACKETS[text[opened[-1]]]:
            opened.pop()
    return opened[0] if opened else end


def _own_part(title, shared):
    rest = title[len(shared):].strip()
    inner = rest[1:-1]
    if rest[:1] in _BRACKETS and rest.endswith(_BRACKETS[rest[0]]) and not any(
            ch in inner for pair in _BRACKETS.items() for ch in pair):
        rest = inner.strip()
    return rest.lstrip(_BREAKS.translate({ord(c): None for c in _BRACKETS})).strip() or title


def summarize(banks):
    """`banks`: dicts with title, time_limit (minutes or None), n_subs, folder (or None), in order.

    Returns count, full (list them in full), shared (title start or ''), limit_text (when all Quiz
    Banks share one Time Limit, else None), folder (when all share one Folder, else None),
    n_subs (total), and items: label plus limit_text / n_subs / folder only where they differ.
    """
    limits = {b['time_limit'] or None for b in banks}
    folders = {b['folder'].id if b.get('folder') else None for b in banks}
    counts = {b['n_subs'] for b in banks}
    same_limit = len(limits) == 1
    shared = _shared_start([b['title'] for b in banks])
    count = len(banks)
    limit_text = None
    if same_limit and banks:
        limit_text = time_limit_text(banks[0]['time_limit'])
        if count > 1:
            limit_text = '全部' + limit_text
    return {
        'count': count,
        'full': count <= FULL_LIST_UP_TO,
        'shared': shared,
        'limit_text': limit_text,
        'folder': banks[0].get('folder') if banks and len(folders) == 1 else None,
        'n_subs': sum(b['n_subs'] for b in banks),
        'items': [{
            'title': b['title'],
            'label': _own_part(b['title'], shared) if shared else b['title'],
            'limit_text': None if same_limit else time_limit_text(b['time_limit'], short=True),
            'n_subs': None if len(counts) == 1 else b['n_subs'],
            'folder': None if len(folders) == 1 else b.get('folder'),
        } for b in banks],
    }
