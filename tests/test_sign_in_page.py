"""HTTP seam: the sign-in page (home page `/`), ticket 02 (#4)."""

import re

from conftest import TEACHER_ROUTER_ID, sign_in


def _home(client, query=''):
    response = client.get('/' + query)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_signed_out_home_is_one_screen_with_one_sign_in_button(client):
    html = _home(client)
    assert '出題、發連結，' in html and '學生掃了就作答' in html
    assert re.search(r'<a [^>]*href="/auth/login"[^>]*>\s*用 VansCoding 帳號登入\s*</a>', html)
    assert '教師登入會前往 VansCoding 登入頁，以 Google 帳號登入。' in html
    assert 'class="top"' not in html  # no top bar
    assert 'role="alert"' not in html and 'role="status"' not in html


def _banner(html):
    match = re.search(r'<div class="[^"]*lp-banner[^"]*" role="(alert|status)">(.*?)</div>', html, re.S)
    assert match, 'no banner'
    return match.group(1), re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', match.group(2))).strip(), match.group(2)


def test_failed_sign_in_says_only_teachers_can_sign_in_and_offers_retry(client):
    role, text, markup = _banner(_home(client, '?error=login_failed'))
    assert role == 'alert'
    assert '登入失敗，請再試一次' in text
    assert '只有教師帳號可以登入後台。' in text
    assert re.search(r'<a href="/auth/login">\s*重新登入 →\s*</a>', markup)


def test_sign_in_service_down_shows_its_banner(client):
    role, text, _ = _banner(_home(client, '?error=router_unavailable'))
    assert role == 'alert'
    assert '驗證服務暫時無法使用，請稍後再試' in text
    assert '只有教師帳號' not in text


def test_unknown_error_code_shows_no_banner(client):
    html = _home(client, '?error=whatever')
    assert 'lp-banner' not in html


def test_teacher_page_without_sign_in_sends_to_home_with_login_required_banner(client):
    response = client.get('/teacher-dashboard')
    assert response.status_code == 302
    location = response.headers['Location']
    assert location.startswith('/?')
    assert 'notice=login_required' in location

    role, text, markup = _banner(_home(client, location[1:]))
    assert role == 'status'
    assert '請先登入教師後台' in text
    # both the banner link and the main button come back to the page asked for
    html = _home(client, location[1:])
    assert html.count('href="/auth/login?next=/teacher-dashboard"') == 2


def test_next_to_another_site_is_dropped(client):
    html = _home(client, '?notice=login_required&next=//evil.test/x')
    assert 'evil.test' not in html
    assert 'href="/auth/login"' in html


def test_signed_in_teacher_sees_enter_dashboard_and_own_name(client):
    sign_in(client, TEACHER_ROUTER_ID, name='林老師')
    html = _home(client)
    assert re.search(r'<a [^>]*href="/teacher-dashboard"[^>]*>\s*進入後台 →\s*</a>', html)
    assert '已登入：林老師' in html
    assert '用 VansCoding 帳號登入' not in html


def test_sign_in_page_colours_come_from_the_tokens(client):
    css = client.get('/static/css/pages/sign_in.css').get_data(as_text=True)
    assert 'var(--hero-bg)' in css
    assert not re.findall(r'#[0-9a-fA-F]{3,8}\b', css)
    assert not re.findall(r'rgba?\(', css)
    tokens = client.get('/static/css/tokens.css').get_data(as_text=True)
    assert re.search(r'--hero-bg\s*:\s*#0F2A24', tokens, re.I)
    for n in range(1, 7):
        assert re.search(rf'--glow-{n}\s*:', tokens)


def test_reduced_motion_shows_a_still_frame(client):
    css = client.get('/static/css/pages/sign_in.css').get_data(as_text=True)
    still = css[css.index('@media (prefers-reduced-motion: reduce)'):]
    assert '.lp-blob' in still and '.sc-typed' in still
    shared = client.get('/static/css/app.css').get_data(as_text=True)
    assert re.search(r'prefers-reduced-motion: reduce\)\s*\{[^}]*animation: none !important', shared)
