"""Teacher sign-in through vans_coding_router (ADR 0007).

The router is the OAuth authorization server. A Teacher signs in with the
`openid teacher` scope (Google only, teacher or admin role). This module keeps
the router user id and Display Name in a signed cookie for 12 hours and keeps
no accounts of its own.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Optional, Protocol

import jwt
from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from itsdangerous import BadSignature, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

TEACHER_COOKIE = 'vq_teacher'
LOGIN_COOKIE = 'vq_teacher_login'
LOGIN_COOKIE_PATH = '/auth'
TEACHER_SESSION_SECONDS = 12 * 60 * 60
LOGIN_SECONDS = 10 * 60
CALLBACK_PATH = '/auth/callback'
SCOPE = 'openid teacher'

DEFAULT_ROUTER_URL = 'https://ai.vanscoding.com'
DEFAULT_PUBLIC_URL = 'https://quizzes.vanscoding.com'
DEFAULT_CLIENT_ID = 'quizzes'
DEFAULT_SECRET_KEY = 'your-secret-key-here'
MIN_SECRET_KEY_LENGTH = 32

ROUTER_UNAVAILABLE_NOTICE = '驗證服務暫時無法使用，請稍後再試'
LOGIN_FAILED_NOTICE = '登入失敗，請再試一次'
LOGIN_REQUIRED_NOTICE = '請先登入教師後台'
BAD_ORIGIN_NOTICE = '請求來源不符，已拒絕'

# Salts keep each signed value to its own purpose, so one cannot stand in for another.
TEACHER_COOKIE_SALT = 'quizzes-teacher-cookie'
LOGIN_COOKIE_SALT = 'quizzes-login-cookie'
FAKE_CODE_SALT = 'quizzes-fake-router-code'

ID_TOKEN_ALGORITHMS = ['RS256', 'ES256']
CLOCK_LEEWAY_SECONDS = 60
DISCOVERY_CACHE_SECONDS = 5 * 60
SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})


def default_display_name(user_id: int) -> str:
    return f'教師 {user_id}'


@dataclass(frozen=True)
class Teacher:
    user_id: int
    display_name: str

    def to_claims(self) -> dict:
        """What the Teacher cookie and the fake router's code carry."""
        return {'uid': self.user_id, 'name': self.display_name}

    @classmethod
    def from_claims(cls, claims) -> Optional['Teacher']:
        """The Teacher in `to_claims` output, or None when the value is not that shape."""
        if not isinstance(claims, dict):
            return None
        user_id, name = claims.get('uid'), claims.get('name')
        if not isinstance(user_id, int) or isinstance(user_id, bool) or not isinstance(name, str):
            return None
        return cls(user_id=user_id, display_name=name)


class LoginError(str, Enum):
    """Why a sign-in did not finish. The value is the `?error=` code on the home page."""

    ROUTER_UNAVAILABLE = 'router_unavailable'
    LOGIN_FAILED = 'login_failed'

    @property
    def notice(self) -> str:
        return ROUTER_UNAVAILABLE_NOTICE if self is LoginError.ROUTER_UNAVAILABLE else LOGIN_FAILED_NOTICE

    @classmethod
    def notice_for(cls, code: Optional[str]) -> Optional[str]:
        """The notice for a `?error=` code, or None for a missing or unknown code."""
        try:
            return cls(code).notice
        except ValueError:
            return None


class LoginRefused(Exception):
    """The router did not sign the Teacher in."""

    def __init__(self, error: LoginError, detail: str):
        super().__init__(f'{error.value}: {detail}')
        self.error = error


def _b64url_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def teacher_from_id_token(claims: dict) -> Teacher:
    sub = claims.get('sub')
    if not isinstance(sub, str) or not sub.isdigit():
        raise LoginRefused(LoginError.LOGIN_FAILED, 'ID token sub')
    user_id = int(sub)
    name = claims.get('name')
    display_name = name.strip() if isinstance(name, str) and name.strip() else default_display_name(user_id)
    return Teacher(user_id=user_id, display_name=display_name)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """The token request carries the client secret, so it must never follow a redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RouterGateway:
    """Talks to the real router: discovery, token exchange, and ID token check."""

    def __init__(self, base_url: str, client_id: str, client_secret: Optional[str], timeout: float = 10.0):
        self.base_url = base_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect)
        self._discovery: Optional[dict] = None
        self._discovery_until = 0.0

    def _discover(self, fresh: bool = False) -> dict:
        """The router's OpenID configuration. `fresh` asks the router now; otherwise an answer
        up to 5 minutes old is reused. Raises LoginRefused when unreachable or not this router."""
        if not fresh and self._discovery is not None and time.monotonic() < self._discovery_until:
            return self._discovery
        discovery = self._get_json(f'{self.base_url}/.well-known/openid-configuration')
        endpoints = ('issuer', 'authorization_endpoint', 'token_endpoint', 'jwks_uri')
        if not all(isinstance(discovery.get(name), str) for name in endpoints):
            raise LoginRefused(LoginError.ROUTER_UNAVAILABLE, 'discovery: unreadable answer')
        if discovery['issuer'].rstrip('/') != self.base_url:
            raise LoginRefused(LoginError.LOGIN_FAILED, f'discovery issuer {discovery["issuer"]!r} is not {self.base_url}')
        self._discovery = discovery
        self._discovery_until = time.monotonic() + DISCOVERY_CACHE_SECONDS
        return discovery

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str, nonce: str) -> str:
        """Asks the router first, so an unreachable router shows the notice instead of a browser error."""
        authorization_endpoint = self._discover(fresh=True)['authorization_endpoint']
        query = urllib.parse.urlencode({
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'scope': SCOPE,
            'state': state,
            'nonce': nonce,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        })
        return f'{authorization_endpoint}?{query}'

    def _request(self, url: str, data: Optional[bytes] = None) -> tuple[int, bytes]:
        headers = {'Accept': 'application/json'}
        if data is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        req = urllib.request.Request(url, data=data, headers=headers, method='POST' if data is not None else 'GET')
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read() or b''
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise LoginRefused(LoginError.ROUTER_UNAVAILABLE, f'{url}: {error}') from None

    def _get_json(self, url: str) -> dict:
        status, body = self._request(url)
        if status != 200:
            raise LoginRefused(LoginError.ROUTER_UNAVAILABLE, f'{url}: HTTP {status}')
        try:
            value = json.loads(body)
        except ValueError:
            raise LoginRefused(LoginError.ROUTER_UNAVAILABLE, f'{url}: unreadable answer') from None
        if not isinstance(value, dict):
            raise LoginRefused(LoginError.ROUTER_UNAVAILABLE, f'{url}: unreadable answer')
        return value

    def complete_login(self, code: str, code_verifier: str, redirect_uri: str, nonce: str) -> Teacher:
        discovery = self._discover()
        issuer = discovery['issuer']
        token_endpoint = discovery['token_endpoint']
        jwks_uri = discovery['jwks_uri']

        form = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': self.client_id,
            'code_verifier': code_verifier,
        }
        if self.client_secret:
            form['client_secret'] = self.client_secret
        status, body = self._request(token_endpoint, urllib.parse.urlencode(form).encode('ascii'))
        if status in (400, 401):
            raise LoginRefused(LoginError.LOGIN_FAILED, f'token: HTTP {status}')
        if status != 200:
            raise LoginRefused(LoginError.ROUTER_UNAVAILABLE, f'token: HTTP {status}')
        try:
            id_token = json.loads(body).get('id_token')
        except (ValueError, AttributeError):
            id_token = None
        if not isinstance(id_token, str):
            raise LoginRefused(LoginError.LOGIN_FAILED, 'token: no id_token')

        jwks = self._get_json(jwks_uri)
        claims = verify_id_token(id_token, jwks, issuer=issuer, audience=self.client_id)
        if claims.get('nonce') != nonce:
            raise LoginRefused(LoginError.LOGIN_FAILED, 'ID token nonce')
        return teacher_from_id_token(claims)


def verify_id_token(id_token: str, jwks: dict, issuer: str, audience: str) -> dict:
    """Checks the signature against the router's JWKS, and `iss`, `aud`, `exp`, `iat`."""
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError:
        raise LoginRefused(LoginError.LOGIN_FAILED, 'ID token header') from None
    alg = header.get('alg')
    if alg not in ID_TOKEN_ALGORITHMS:
        raise LoginRefused(LoginError.LOGIN_FAILED, f'ID token alg {alg!r}')
    keys = jwks.get('keys')
    if not isinstance(keys, list):
        raise LoginRefused(LoginError.ROUTER_UNAVAILABLE, 'jwks: unreadable answer')
    kid = header.get('kid')
    for jwk in keys:
        if not isinstance(jwk, dict):
            continue
        if kid is not None and jwk.get('kid') != kid:
            continue
        if jwk.get('alg') not in (None, alg):
            continue
        try:
            key = jwt.PyJWK(jwk, algorithm=alg)
            return jwt.decode(
                id_token,
                key=key.key,
                algorithms=[alg],
                audience=audience,
                issuer=issuer,
                leeway=CLOCK_LEEWAY_SECONDS,
                options={'require': ['iss', 'aud', 'sub', 'exp']},
            )
        except jwt.PyJWTError:
            continue
    raise LoginRefused(LoginError.LOGIN_FAILED, 'ID token signature or claims')


class FakeRouterGateway:
    """Development only: a local page stands in for the router's Authorization Page."""

    def __init__(self, secret_key: str):
        self._codes = URLSafeTimedSerializer(secret_key, salt=FAKE_CODE_SALT)

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str, nonce: str) -> str:
        return url_for(
            'teacher_auth.fake_authorize',
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            nonce=nonce,
        )

    def issue_code(self, teacher: Teacher, code_challenge: str, nonce: str) -> str:
        return self._codes.dumps({**teacher.to_claims(), 'cc': code_challenge, 'nonce': nonce})

    def complete_login(self, code: str, code_verifier: str, redirect_uri: str, nonce: str) -> Teacher:
        try:
            grant = self._codes.loads(code, max_age=300)
        except BadSignature:
            raise LoginRefused(LoginError.LOGIN_FAILED, 'fake code') from None
        teacher = Teacher.from_claims(grant)
        if teacher is None or grant.get('cc') != _b64url_sha256(code_verifier) or grant.get('nonce') != nonce:
            raise LoginRefused(LoginError.LOGIN_FAILED, 'fake code PKCE or nonce')
        return teacher


class Gateway(Protocol):
    """What the sign-in routes need from the router: RouterGateway, or FakeRouterGateway in development."""

    def authorize_url(self, redirect_uri: str, state: str, code_challenge: str, nonce: str) -> str: ...

    def complete_login(self, code: str, code_verifier: str, redirect_uri: str, nonce: str) -> Teacher: ...


@dataclass
class TeacherAuthSettings:
    gateway: Gateway
    public_url: Optional[str]
    secure_cookies: bool


def check_secret_key(secret_key: Optional[str], environment: str) -> None:
    """The secret key signs the Teacher cookie, so production refuses a weak one."""
    if environment != 'production':
        return
    if not secret_key or secret_key == DEFAULT_SECRET_KEY or len(secret_key) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(
            f'SECRET_KEY must be set to a random value of at least {MIN_SECRET_KEY_LENGTH} characters in production.'
        )


KNOWN_ENVIRONMENTS = ('development', 'production')


def check_environment(environment: Optional[str]) -> str:
    """FLASK_ENV must be named exactly. A missing or misspelled value would otherwise
    fall back to development and open the fake router in production."""
    if environment not in KNOWN_ENVIRONMENTS:
        raise RuntimeError(f'FLASK_ENV must be one of {", ".join(KNOWN_ENVIRONMENTS)}; got {environment!r}.')
    return environment


def configure_teacher_auth(app, environment: Optional[str], env=os.environ) -> TeacherAuthSettings:
    environment = check_environment(environment)
    check_secret_key(app.config.get('SECRET_KEY'), environment)
    is_production = environment == 'production'
    router_url = env.get('ROUTER_URL') or ''
    client_id = env.get('QUIZZES_OAUTH_CLIENT_ID') or DEFAULT_CLIENT_ID
    client_secret = env.get('QUIZZES_OAUTH_CLIENT_SECRET') or None

    if is_production:
        if not client_secret:
            raise RuntimeError('QUIZZES_OAUTH_CLIENT_SECRET must be set in production.')
        gateway = RouterGateway(router_url or DEFAULT_ROUTER_URL, client_id, client_secret)
        public_url = env.get('PUBLIC_URL') or DEFAULT_PUBLIC_URL
    elif router_url:
        gateway = RouterGateway(router_url, client_id, client_secret)
        public_url = env.get('PUBLIC_URL') or None
    else:
        gateway = FakeRouterGateway(app.config['SECRET_KEY'])
        public_url = env.get('PUBLIC_URL') or None

    settings = TeacherAuthSettings(
        gateway=gateway,
        public_url=public_url.rstrip('/') if public_url else None,
        secure_cookies=is_production,
    )
    app.extensions['teacher_auth'] = settings
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=is_production,
    )
    app.register_blueprint(teacher_auth)

    @app.context_processor
    def _inject_teacher():
        return {'current_teacher': current_teacher()}

    return settings


def _settings() -> TeacherAuthSettings:
    return current_app.extensions['teacher_auth']


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=salt)


def own_origin() -> str:
    public_url = _settings().public_url
    if public_url:
        parts = urllib.parse.urlsplit(public_url)
        return f'{parts.scheme}://{parts.netloc}'
    return request.host_url.rstrip('/')


def callback_url() -> str:
    """The redirect URI registered on the router for this site."""
    return own_origin() + CALLBACK_PATH


def origin_is_own() -> bool:
    return (request.headers.get('Origin') or '').rstrip('/') == own_origin()


def refuse_bad_origin():
    """A write from another origin, even another *.vanscoding.com site, is refused (ADR 0007)."""
    return jsonify({'error': BAD_ORIGIN_NOTICE}), 403


def sign_teacher_cookie(teacher: Teacher) -> str:
    return _serializer(TEACHER_COOKIE_SALT).dumps(teacher.to_claims())


def current_teacher() -> Optional[Teacher]:
    """The signed-in Teacher, or None when the cookie is missing, forged, or older than 12 hours."""
    if 'teacher' in g:
        return g.teacher
    teacher = None
    value = request.cookies.get(TEACHER_COOKIE)
    if value:
        try:
            claims = _serializer(TEACHER_COOKIE_SALT).loads(value, max_age=TEACHER_SESSION_SECONDS)
        except BadSignature:
            claims = None
        teacher = Teacher.from_claims(claims)
    g.teacher = teacher
    return teacher


def teacher_required(view):
    """Pages and APIs for a signed-in Teacher. A write must come from this site's own origin."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.method not in SAFE_METHODS and not origin_is_own():
            return refuse_bad_origin()
        if current_teacher() is None:
            if request.path.startswith('/api/'):
                return jsonify({'error': LOGIN_REQUIRED_NOTICE}), 401
            return redirect(url_for('teacher_auth.login', next=request.full_path.rstrip('?')))
        return view(*args, **kwargs)

    return wrapper


def safe_next(value: Optional[str]) -> str:
    """Only a path on this site; never another host (no open redirect)."""
    if value and value.startswith('/') and not value.startswith('//') and '\\' not in value:
        return value
    return '/teacher-dashboard'


def _cookie_kwargs(max_age: int, path: str = '/') -> dict:
    return {
        'max_age': max_age,
        'path': path,
        'httponly': True,
        'secure': _settings().secure_cookies,
        'samesite': 'Lax',
    }


teacher_auth = Blueprint('teacher_auth', __name__)


@teacher_auth.route('/auth/login')
def login():
    next_path = safe_next(request.args.get('next'))
    if current_teacher() is not None:
        return redirect(next_path)
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(24)
    pending = _serializer(LOGIN_COOKIE_SALT).dumps(
        {'state': state, 'verifier': verifier, 'nonce': nonce, 'next': next_path}
    )
    try:
        authorize_url = _settings().gateway.authorize_url(
            redirect_uri=callback_url(),
            state=state,
            code_challenge=_b64url_sha256(verifier),
            nonce=nonce,
        )
    except LoginRefused as refused:
        logger.warning('Teacher login could not start: %s', refused)
        return redirect(url_for('index', error=refused.error.value))
    response = redirect(authorize_url)
    response.set_cookie(LOGIN_COOKIE, pending, **_cookie_kwargs(LOGIN_SECONDS, LOGIN_COOKIE_PATH))
    return response


@teacher_auth.route(CALLBACK_PATH)
def callback():
    def fail(error: LoginError):
        response = redirect(url_for('index', error=error.value))
        response.delete_cookie(LOGIN_COOKIE, path=LOGIN_COOKIE_PATH)
        return response

    try:
        pending = _serializer(LOGIN_COOKIE_SALT).loads(request.cookies.get(LOGIN_COOKIE, ''), max_age=LOGIN_SECONDS)
    except BadSignature:
        pending = None
    code = request.args.get('code')
    state = request.args.get('state')
    if (
        not isinstance(pending, dict)
        or not code
        or not state
        or not secrets.compare_digest(state, str(pending.get('state', '')))
    ):
        return fail(LoginError.LOGIN_FAILED)

    try:
        teacher = _settings().gateway.complete_login(
            code=code,
            code_verifier=pending['verifier'],
            redirect_uri=callback_url(),
            nonce=pending['nonce'],
        )
    except LoginRefused as refused:
        logger.warning('Teacher login refused: %s', refused)
        return fail(refused.error)

    response = redirect(safe_next(pending.get('next')))
    response.set_cookie(TEACHER_COOKIE, sign_teacher_cookie(teacher), **_cookie_kwargs(TEACHER_SESSION_SECONDS))
    response.delete_cookie(LOGIN_COOKIE, path=LOGIN_COOKIE_PATH)
    return response


@teacher_auth.route('/auth/logout', methods=['POST'])
def logout():
    if not origin_is_own():
        return refuse_bad_origin()
    response = redirect(url_for('index'), code=303)
    response.delete_cookie(TEACHER_COOKIE, path='/')
    return response


@teacher_auth.route('/dev/fake-router/authorize', methods=['GET', 'POST'])
def fake_authorize():
    """Development only. Production never builds a FakeRouterGateway, so this answers 404 there."""
    gateway = _settings().gateway
    if not isinstance(gateway, FakeRouterGateway):
        return 'Not Found', 404
    params = request.values
    redirect_uri = params.get('redirect_uri', '')
    if redirect_uri != callback_url():
        return 'redirect_uri does not match this site', 400
    if request.method == 'GET':
        return render_template('fake_router_authorize.html', params=params)
    try:
        user_id = int(params.get('user_id', ''))
    except ValueError:
        return 'user_id must be a number', 400
    display_name = (params.get('display_name') or '').strip() or default_display_name(user_id)
    teacher = Teacher(user_id=user_id, display_name=display_name)
    code = gateway.issue_code(teacher, params.get('code_challenge', ''), params.get('nonce', ''))
    query = urllib.parse.urlencode({'code': code, 'state': params.get('state', '')})
    return redirect(f'{redirect_uri}?{query}')
