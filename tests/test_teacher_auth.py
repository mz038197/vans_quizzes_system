"""Teacher sign-in through the router (ADR 0007)."""
import json
import time
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask

import app as app_module
import teacher_auth
from conftest import OWN_ORIGIN, TEACHER_ROUTER_ID, sign_in


def _location(response):
    return response.headers['Location']


def _query(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


# --- access control -------------------------------------------------------

def test_teacher_page_without_sign_in_redirects_to_login(client):
    response = client.get('/teacher-dashboard')
    assert response.status_code == 302
    assert _location(response).startswith("/?notice=login_required&next=")


def test_teacher_api_without_sign_in_is_401(client):
    response = client.get(f"/api/quiz-bank/{client._ids['quiz_bank_id']}/submissions")
    assert response.status_code == 401
    assert response.get_json()['error'] == teacher_auth.LOGIN_REQUIRED_NOTICE


def test_signed_in_teacher_sees_own_dashboard(auth_client):
    response = auth_client.get('/teacher-dashboard')
    assert response.status_code == 200
    assert 'Timed Bank' in response.get_data(as_text=True)
    assert '測試老師' in response.get_data(as_text=True)


def test_other_teacher_cannot_touch_the_bank(client):
    sign_in(client, TEACHER_ROUTER_ID + 1)
    client.environ_base['HTTP_ORIGIN'] = OWN_ORIGIN
    quiz_bank_id = client._ids['quiz_bank_id']
    assert client.get(f'/api/quiz-bank/{quiz_bank_id}/submissions').status_code == 403
    assert client.delete(f'/api/quiz-bank/{quiz_bank_id}').status_code == 403
    assert 'Timed Bank' not in client.get('/teacher-dashboard').get_data(as_text=True)


@pytest.mark.parametrize('origin', [None, 'https://club.vanscoding.com', 'http://localhost.evil.test'])
def test_teacher_write_from_another_origin_is_refused(client, origin):
    sign_in(client, TEACHER_ROUTER_ID)
    headers = {'Origin': origin} if origin else {}
    response = client.post(f"/api/quiz-bank/{client._ids['quiz_bank_id']}/toggle", headers=headers)
    assert response.status_code == 403
    with app_module.app.app_context():
        assert app_module.db.session.get(app_module.QuizBank, client._ids['quiz_bank_id']).is_active


def test_forged_cookie_is_not_a_teacher(client):
    client.set_cookie(teacher_auth.TEACHER_COOKIE, 'eyJ1aWQiOjQyLCJuYW1lIjoieCJ9.forged')
    assert client.get('/teacher-dashboard').status_code == 302


def test_cookie_older_than_twelve_hours_is_not_a_teacher(client, monkeypatch):
    real_time = time.time
    monkeypatch.setattr(time, 'time', lambda: real_time() - teacher_auth.TEACHER_SESSION_SECONDS - 5)
    sign_in(client, TEACHER_ROUTER_ID)
    monkeypatch.setattr(time, 'time', real_time)
    assert client.get('/teacher-dashboard').status_code == 302


# --- sign-in flow (development fake router) -------------------------------

def test_full_sign_in_with_the_fake_router(client):
    start = client.get('/auth/login?next=/quiz-bank/1')
    assert start.status_code == 302
    fake_page = _location(start)
    assert fake_page.startswith('/dev/fake-router/authorize?')
    params = _query(fake_page)
    assert params['redirect_uri'] == OWN_ORIGIN + '/auth/callback'

    approved = client.post('/dev/fake-router/authorize', data={**params, 'user_id': '42', 'display_name': '王老師'})
    callback = _location(approved)
    assert callback.startswith(OWN_ORIGIN + '/auth/callback?')

    finished = client.get(callback[len(OWN_ORIGIN):])
    assert finished.status_code == 302
    assert _location(finished) == '/quiz-bank/1'
    page = client.get('/teacher-dashboard')
    assert page.status_code == 200
    assert '王老師' in page.get_data(as_text=True)


def test_callback_with_wrong_state_fails(client):
    start = client.get('/auth/login')
    params = _query(_location(start))
    approved = client.post('/dev/fake-router/authorize', data={**params, 'user_id': '42'})
    callback = _query(_location(approved))
    response = client.get('/auth/callback', query_string={'code': callback['code'], 'state': 'not-the-state'})
    assert _location(response) == '/?error=login_failed'
    assert client.get('/teacher-dashboard').status_code == 302


def test_callback_without_login_cookie_fails(client):
    response = client.get('/auth/callback?code=x&state=y')
    assert _location(response) == '/?error=login_failed'


def test_router_unreachable_shows_the_notice(client, monkeypatch):
    settings = app_module.app.extensions['teacher_auth']

    def unavailable(**kwargs):
        raise teacher_auth.LoginRefused(teacher_auth.LoginError.ROUTER_UNAVAILABLE, 'test')

    start = client.get('/auth/login')
    params = _query(_location(start))
    approved = client.post('/dev/fake-router/authorize', data={**params, 'user_id': '42'})
    monkeypatch.setattr(settings.gateway, 'complete_login', unavailable)
    response = client.get(_location(approved)[len(OWN_ORIGIN):])
    assert _location(response) == '/?error=router_unavailable'
    home = client.get('/?error=router_unavailable').get_data(as_text=True)
    assert teacher_auth.ROUTER_UNAVAILABLE_NOTICE in home


def test_logout_is_post_from_own_origin(auth_client):
    assert auth_client.get('/auth/logout').status_code == 405
    refused = auth_client.post('/auth/logout', headers={'Origin': 'https://evil.test'})
    assert refused.status_code == 403
    response = auth_client.post('/auth/logout')
    assert response.status_code == 303
    assert auth_client.get('/teacher-dashboard').status_code == 302


@pytest.mark.parametrize('value', ['//evil.test/x', 'https://evil.test', '/\\evil.test', '', None])
def test_next_never_leaves_the_site(value):
    assert teacher_auth.safe_next(value) == '/teacher-dashboard'


def test_next_keeps_a_local_path():
    assert teacher_auth.safe_next('/quiz-bank/3?tab=1') == '/quiz-bank/3?tab=1'


def test_old_password_routes_are_gone(client):
    assert client.get('/login').status_code == 404
    assert client.post('/register', json={}).status_code == 404


# --- production settings ---------------------------------------------------

@pytest.mark.parametrize('secret', [None, '', teacher_auth.DEFAULT_SECRET_KEY, 'short'])
def test_production_refuses_a_weak_secret_key(secret):
    with pytest.raises(RuntimeError):
        teacher_auth.check_secret_key(secret, 'production')


def test_development_allows_the_default_secret_key():
    teacher_auth.check_secret_key(teacher_auth.DEFAULT_SECRET_KEY, 'development')


def test_production_needs_the_client_secret():
    fresh = Flask('production-check')
    fresh.config['SECRET_KEY'] = 'x' * 40
    with pytest.raises(RuntimeError):
        teacher_auth.configure_teacher_auth(fresh, 'production', env={})


def test_production_never_uses_the_fake_router():
    fresh = Flask('production-gateway')
    fresh.config['SECRET_KEY'] = 'x' * 40
    settings = teacher_auth.configure_teacher_auth(
        fresh, 'production', env={'QUIZZES_OAUTH_CLIENT_SECRET': 's'}
    )
    assert isinstance(settings.gateway, teacher_auth.RouterGateway)
    assert settings.gateway.base_url == teacher_auth.DEFAULT_ROUTER_URL
    assert settings.public_url == teacher_auth.DEFAULT_PUBLIC_URL
    assert settings.secure_cookies
    assert fresh.config['SESSION_COOKIE_SECURE'] is True
    with fresh.test_client() as c:
        assert c.get('/dev/fake-router/authorize').status_code == 404


# --- real router gateway ---------------------------------------------------

ISSUER = 'https://router.test'
CLIENT_ID = 'quizzes'


@pytest.fixture(scope='module')
def signing_key():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({'kid': 'k1', 'alg': 'RS256', 'use': 'sig'})
    return private_key, {'keys': [jwk]}


def _id_token(private_key, **overrides):
    now = int(time.time())
    claims = {'iss': ISSUER, 'aud': CLIENT_ID, 'sub': '42', 'name': '王老師', 'iat': now, 'exp': now + 300,
              'nonce': 'n1'}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, private_key, algorithm='RS256', headers={'kid': 'k1'})


class _FakeRouter(teacher_auth.RouterGateway):
    """RouterGateway with the HTTP layer replaced by canned answers."""

    def __init__(self, jwks, token_status=200, token_body=None):
        super().__init__(ISSUER, CLIENT_ID, 'client-secret')
        self.jwks = jwks
        self.token_status = token_status
        self.token_body = token_body
        self.token_form = None

    def _request(self, url, data=None):
        if url.endswith('/.well-known/openid-configuration'):
            return 200, json.dumps({'issuer': ISSUER, 'authorization_endpoint': ISSUER + '/oauth/authorize',
                                    'token_endpoint': ISSUER + '/oauth/token',
                                    'jwks_uri': ISSUER + '/oauth/jwks'}).encode()
        if url.endswith('/oauth/jwks'):
            return 200, json.dumps(self.jwks).encode()
        self.token_form = parse_qs(data.decode())
        return self.token_status, json.dumps(self.token_body or {}).encode()


def test_router_login_returns_the_teacher(signing_key):
    private_key, jwks = signing_key
    gateway = _FakeRouter(jwks, token_body={'id_token': _id_token(private_key)})
    teacher = gateway.complete_login(code='c', code_verifier='v', redirect_uri='https://q/auth/callback', nonce='n1')
    assert teacher == teacher_auth.Teacher(user_id=42, display_name='王老師')
    assert gateway.token_form['client_secret'] == ['client-secret']
    assert gateway.token_form['code_verifier'] == ['v']


@pytest.mark.parametrize('overrides', [
    {'aud': 'someone-else'},
    {'iss': 'https://evil.test'},
    {'exp': int(time.time()) - 3600},
    {'nonce': 'other'},
    {'sub': 'not-a-number'},
    {'exp': None},
])
def test_router_login_refuses_a_bad_id_token(signing_key, overrides):
    private_key, jwks = signing_key
    gateway = _FakeRouter(jwks, token_body={'id_token': _id_token(private_key, **overrides)})
    with pytest.raises(teacher_auth.LoginRefused) as refused:
        gateway.complete_login(code='c', code_verifier='v', redirect_uri='r', nonce='n1')
    assert refused.value.error is teacher_auth.LoginError.LOGIN_FAILED


def test_router_login_refuses_a_token_signed_by_another_key(signing_key):
    _, jwks = signing_key
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    gateway = _FakeRouter(jwks, token_body={'id_token': _id_token(other_key)})
    with pytest.raises(teacher_auth.LoginRefused):
        gateway.complete_login(code='c', code_verifier='v', redirect_uri='r', nonce='n1')


def test_router_login_refuses_an_unsigned_token(signing_key):
    _, jwks = signing_key
    unsigned = jwt.encode({'iss': ISSUER, 'aud': CLIENT_ID, 'sub': '42', 'exp': int(time.time()) + 60,
                           'nonce': 'n1'}, None, algorithm='none')
    gateway = _FakeRouter(jwks, token_body={'id_token': unsigned})
    with pytest.raises(teacher_auth.LoginRefused):
        gateway.complete_login(code='c', code_verifier='v', redirect_uri='r', nonce='n1')


@pytest.mark.parametrize('status,error', [
    (400, teacher_auth.LoginError.LOGIN_FAILED),
    (401, teacher_auth.LoginError.LOGIN_FAILED),
    (500, teacher_auth.LoginError.ROUTER_UNAVAILABLE),
])
def test_router_token_errors(signing_key, status, error):
    _, jwks = signing_key
    gateway = _FakeRouter(jwks, token_status=status)
    with pytest.raises(teacher_auth.LoginRefused) as refused:
        gateway.complete_login(code='c', code_verifier='v', redirect_uri='r', nonce='n1')
    assert refused.value.error is error


def test_authorize_url_asks_for_openid_teacher_with_pkce(signing_key):
    gateway = _FakeRouter(signing_key[1])
    url = gateway.authorize_url(redirect_uri='https://q/auth/callback', state='s', code_challenge='cc', nonce='n')
    params = _query(url)
    assert url.startswith(ISSUER + '/oauth/authorize?')
    assert params['scope'] == 'openid teacher'
    assert params['code_challenge_method'] == 'S256'
    assert params['nonce'] == 'n'
    assert 'client_secret' not in params
    assert 'client-secret' not in url


# --- FLASK_ENV gate (code review: the fake router must need FLASK_ENV=development exactly) ---

@pytest.mark.parametrize('environment', [None, '', 'prod', 'Development', 'staging'])
def test_unknown_flask_env_refuses_to_start(environment):
    fresh = Flask('env-check')
    fresh.config['SECRET_KEY'] = 'x' * 40
    with pytest.raises(RuntimeError):
        teacher_auth.configure_teacher_auth(fresh, environment, env={})


def test_only_development_uses_the_fake_router():
    fresh = Flask('env-dev')
    fresh.config['SECRET_KEY'] = 'dev'
    settings = teacher_auth.configure_teacher_auth(fresh, 'development', env={})
    assert isinstance(settings.gateway, teacher_auth.FakeRouterGateway)


def test_login_start_with_router_unreachable_shows_the_notice(client, monkeypatch):
    settings = app_module.app.extensions['teacher_auth']

    def unreachable(**kwargs):
        raise teacher_auth.LoginRefused(teacher_auth.LoginError.ROUTER_UNAVAILABLE, 'router down')

    monkeypatch.setattr(settings.gateway, 'authorize_url', unreachable)
    response = client.get('/auth/login')
    assert response.status_code == 302
    assert _location(response) == '/?error=router_unavailable'


def test_real_gateway_reads_the_authorize_endpoint_from_discovery(signing_key):
    _, jwks = signing_key
    gateway = _FakeRouter(jwks)
    url = gateway.authorize_url(redirect_uri='r', state='s', code_challenge='c', nonce='n')
    assert url.startswith(ISSUER + '/oauth/authorize?')


def test_real_gateway_authorize_url_fails_when_router_is_down():
    gateway = teacher_auth.RouterGateway('http://127.0.0.1:9', CLIENT_ID, None, timeout=1)
    with pytest.raises(teacher_auth.LoginRefused) as refused:
        gateway.authorize_url(redirect_uri='r', state='s', code_challenge='c', nonce='n')
    assert refused.value.error is teacher_auth.LoginError.ROUTER_UNAVAILABLE


# --- second review ---------------------------------------------------------

def test_login_start_asks_the_router_every_time(signing_key):
    """A cached discovery answer would hide a router that went down since (F3)."""
    calls = []

    class Counting(_FakeRouter):
        def _request(self, url, data=None):
            calls.append(url)
            return super()._request(url, data)

    gateway = Counting(signing_key[1])
    for _ in range(2):
        gateway.authorize_url(redirect_uri='r', state='s', code_challenge='c', nonce='n')
    assert sum(url.endswith('/.well-known/openid-configuration') for url in calls) == 2


def test_router_naming_another_issuer_is_refused(signing_key):
    private_key, jwks = signing_key

    class OtherIssuer(_FakeRouter):
        def _request(self, url, data=None):
            status, body = super()._request(url, data)
            if url.endswith('/.well-known/openid-configuration'):
                body = body.replace(ISSUER.encode(), b'https://evil.test')
            return status, body

    gateway = OtherIssuer(jwks, token_body={'id_token': _id_token(private_key, iss='https://evil.test')})
    with pytest.raises(teacher_auth.LoginRefused) as refused:
        gateway.complete_login(code='c', code_verifier='v', redirect_uri='r', nonce='n1')
    assert refused.value.error is teacher_auth.LoginError.LOGIN_FAILED


def test_token_answer_without_id_token_is_a_failed_login(signing_key):
    gateway = _FakeRouter(signing_key[1], token_body={'access_token': 'x'})
    with pytest.raises(teacher_auth.LoginRefused) as refused:
        gateway.complete_login(code='c', code_verifier='v', redirect_uri='r', nonce='n1')
    assert refused.value.error is teacher_auth.LoginError.LOGIN_FAILED
