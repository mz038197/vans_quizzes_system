"""HTTP seam: the shared design system (style A) reaches every page.

Ticket 01 (#3). Pages, stylesheets and scripts are read through the Flask test client.
"""

import re

import pytest

from conftest import live_code, sign_in, TEACHER_ROUTER_ID

REQUIRED_TOKENS = [
    # colours (clean spec)
    '--primary', '--primary-hover', '--primary-soft', '--secondary',
    '--success', '--success-soft', '--warning', '--warning-soft', '--danger', '--danger-soft',
    '--surface', '--bg', '--border', '--text', '--muted', '--focus',
    # 8-point spacing
    '--s1', '--s2', '--s3', '--s4', '--s5',
    # fonts
    '--font', '--display', '--mono',
    # click target
    '--tap',
    # six question-type colours
    '--type-single', '--type-multi', '--type-fill', '--type-dd', '--type-dfill', '--type-parsons',
    # six Folder colours
    '--f-blue', '--f-green', '--f-purple', '--f-amber', '--f-pink', '--f-cyan',
]

HEX = re.compile(r'#[0-9a-fA-F]{3,8}\b')
BROWSER_DIALOG = re.compile(r'\b(alert|confirm|prompt)\(')


def _text(response):
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


def _submission_token(client):
    ids = client._ids
    response = client.post(
        f'/api/quiz/{live_code(client)}/submit',
        json={'student_name': '學生甲', 'student_email': '', 'quiz_bank_id': ids['quiz_bank_id'], 'answers': {str(ids['question_id']): 'A'}},
    )
    assert response.status_code == 200
    return response.get_json()['result_url'].rsplit('/', 1)[-1]


def test_token_stylesheet_defines_every_token(client):
    css = _text(client.get('/static/css/tokens.css'))
    for token in REQUIRED_TOKENS:
        assert re.search(re.escape(token) + r'\s*:', css), token
    assert '#3B82F6' in css.upper()


TEACHER_PAGES = [
    '/teacher-dashboard',
    '/quiz-banks',
    '/create-quiz-bank',
    '/quiz-bank/{qb}',
    '/quiz-bank/{qb}/submissions',
    '/class-sessions',
]


@pytest.mark.parametrize('path', TEACHER_PAGES)
def test_teacher_pages_use_the_shared_layout(auth_client, path):
    html = _text(auth_client.get(path.format(qb=auth_client._ids['quiz_bank_id'])))
    assert '/static/css/tokens.css' in html
    assert '/static/css/app.css' in html
    assert '/static/js/ui.js' in html
    assert 'class="top"' in html
    assert '測試老師' in html  # signed-in Teacher name in the top bar
    assert 'aria-current="page"' in html  # one nav item is marked active


def test_dashboard_marks_dashboard_as_the_active_area(auth_client):
    html = _text(auth_client.get('/teacher-dashboard'))
    active = re.search(r'<a [^>]*aria-current="page"[^>]*>(.*?)</a>', html, re.S)
    assert active and '儀表板' in active.group(1)


def test_quiz_bank_pages_mark_quiz_banks_as_the_active_area(auth_client):
    html = _text(auth_client.get(f'/quiz-bank/{auth_client._ids["quiz_bank_id"]}'))
    active = re.search(r'<a [^>]*aria-current="page"[^>]*>(.*?)</a>', html, re.S)
    assert active and '題庫' in active.group(1)


def test_student_pages_use_the_shared_layout_without_teacher_nav(client):
    token = _submission_token(client)
    for path in [f'/quiz/{live_code(client)}', f'/result/{token}']:
        html = _text(client.get(path))
        assert '/static/css/tokens.css' in html, path
        assert '/static/css/app.css' in html, path
        assert '/static/js/ui.js' in html, path
        assert 'class="top"' in html, path
        assert '儀表板' not in html, path
        assert '登出' not in html, path


@pytest.mark.parametrize('path', ['/static/css/app.css', '/static/css/qr_stage.css',
                                  '/static/css/pages/dashboard.css', '/static/css/pages/quiz_banks.css',
                                  '/static/css/class_session_dialog.css', '/static/css/pages/quiz.css'])
def test_shared_stylesheets_take_every_colour_from_the_tokens(client, path):
    css = _text(client.get(path))
    assert not HEX.findall(css)
    assert not re.findall(r'rgba?\(', css)
    assert not re.findall(r'\b(white|black)\b(?!-)', css)


def test_buttons_and_inputs_are_at_least_40px_high(client):
    tokens = _text(client.get('/static/css/tokens.css'))
    tap = int(re.search(r'--tap\s*:\s*(\d+)px', tokens).group(1))
    assert tap >= 40
    css = _text(client.get('/static/css/app.css'))
    for selector in [r'\.btn \{', r'\.inp \{', r'\.top-nav a \{']:
        rule = re.search(selector + r'[^}]*\}', css).group(0)
        assert 'min-height: var(--tap)' in rule, selector


def test_focus_outline_is_visible(client):
    css = _text(client.get('/static/css/app.css'))
    assert re.search(r':focus-visible\s*\{[^}]*outline:\s*3px solid var\(--focus\)', css)


def _all_pages(auth_client):
    qb = auth_client._ids['quiz_bank_id']
    token = _submission_token(auth_client)
    pages = [
        '/', '/teacher-dashboard', '/quiz-banks', '/create-quiz-bank', f'/quiz-bank/{qb}',
        f'/quiz-bank/{qb}/submissions', f'/quiz-bank/{qb}/export-pdf',
        f'/quiz/{live_code(auth_client)}', f'/result/{token}',
    ]
    return pages


def test_no_page_uses_browser_dialog_boxes(auth_client):
    for path in _all_pages(auth_client):
        html = _text(auth_client.get(path))
        assert not BROWSER_DIALOG.findall(html), path


@pytest.mark.parametrize('path', ['/static/js/main.js', '/static/js/ui.js',
                                  '/static/js/pages/dashboard.js', '/static/js/pages/quiz_banks.js',
                                  '/static/js/class_session_dialog.js', '/static/js/pages/class_session_gate.js'])
def test_shared_scripts_use_no_browser_dialog_boxes(client, path):
    js = _text(client.get(path))
    assert not BROWSER_DIALOG.findall(js)


def test_ui_script_offers_dialog_and_toast(client):
    js = _text(client.get('/static/js/ui.js'))
    for name in ['toast', 'dialog', 'ask', 'tell', 'askText', 'setStudentName']:
        assert re.search(r'window\.UI = \{[^}]*\b' + name + r'\b', js), name


def test_one_js_escape_helper(client):
    """Review fix 16: UI.escape in static/js/ui.js is the only HTML escape function."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    files = [p for p in list((root / 'templates').glob('*.html')) + list((root / 'static' / 'js').rglob('*.js'))
             if 'vendor' not in p.parts]
    defining = [p.name for p in files if "'&amp;'" in p.read_text(encoding='utf-8')]
    assert defining == ['ui.js']
    for name in ('class_session_dialog.js', 'md_preview.js'):
        assert 'UI.escape(' in (root / 'static' / 'js' / name).read_text(encoding='utf-8')
    for name in ('create_quiz_bank.html', 'manage_quiz_bank.html', 'submissions.html'):
        assert 'UI.escape' in (root / 'templates' / name).read_text(encoding='utf-8')


# Raw px sizes for font-size, gap, padding and margin are not allowed in the site's stylesheets
# (review fix 9): use --fs-*, --s0..--s5 (and --s1-5). Allowed: 0, 1px (borders, hairline offsets),
# and the documented exceptions below.
SIZE_PROP = re.compile(r'(?<![\w-])(font-size|gap|row-gap|column-gap|padding(?:-[a-z]+)*|margin(?:-[a-z]+)*)\s*:\s*([^;}]+)')
SIZE_EXCEPTIONS = (
    'calc(var(--indent, 0) * 20px)',  # quiz_bank.css: one Parsons indent level is 20px, as on the take page
)


def _raw_sizes(css):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    found = []
    for prop, value in SIZE_PROP.findall(css):
        for exception in SIZE_EXCEPTIONS:
            value = value.replace(exception, '')
        found += [f'{prop}: {v}' for v in re.findall(r'(?<![\w.])-?\d*\.?\d+(?:px|rem|em)\b', value)
                  if v.lstrip('-') not in ('0px', '1px')]
    return found


def _site_stylesheets():
    import pathlib
    css_dir = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'css'
    return [p for p in sorted(css_dir.rglob('*.css')) if p.name != 'tokens.css']


@pytest.mark.parametrize('path', _site_stylesheets(), ids=lambda p: p.name)
def test_stylesheets_take_sizes_from_the_tokens(path):
    assert _raw_sizes(path.read_text(encoding='utf-8')) == []


def test_raw_size_check_catches_px_and_allows_borders():
    assert _raw_sizes('.a { font-size: 13px; padding: 0 1px 12px; margin: -1px; }') == ['font-size: 13px', 'padding: 12px']
    assert _raw_sizes('.a { gap: var(--s1); border: 2px solid; margin-left: calc(var(--indent, 0) * 20px); }') == []
