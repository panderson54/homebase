from urllib.parse import parse_qs, urlsplit

import pytest
from authlib.integrations.base_client import OAuthError

from app import auth_service, create_app
from app.models import Household, User
from app.routes.helpers import safe_next_path

GOOGLE_METADATA = {
    'issuer': 'https://accounts.google.com',
    'authorization_endpoint': 'https://accounts.google.com/o/oauth2/v2/auth',
    'token_endpoint': 'https://oauth2.googleapis.com/token',
    'jwks_uri': 'https://www.googleapis.com/oauth2/v3/certs',
}
ALLOWED = frozenset({'homeowner@example.com', 'pmanderson@gmail.com'})


def _claims(email='homeowner@example.com', sub='google-sub-homeowner', verified=True, name='Homeowner'):
    return {'sub': sub, 'email': email, 'email_verified': verified, 'name': name}


@pytest.fixture
def google(app, monkeypatch):
    """The app's real Authlib client, with discovery stubbed so nothing hits the network."""
    client = app.extensions['google_oauth']
    monkeypatch.setattr(client, 'load_server_metadata', lambda: GOOGLE_METADATA)
    return client


@pytest.fixture
def google_returns(google, monkeypatch):
    def _set(claims):
        monkeypatch.setattr(google, 'authorize_access_token', lambda: {'userinfo': claims})
    return _set


class TestSafeNextPath:
    @pytest.mark.parametrize('target', ['/dashboard', '/appliances/3?tab=docs'])
    def test_same_site_paths_pass(self, target):
        assert safe_next_path(target) == target

    @pytest.mark.parametrize('target', [
        None, '', 'dashboard', 'https://evil.example/', '//evil.example/',
        '/\\evil.example', '/\t/evil.example', '/\n/evil.example',
    ])
    def test_off_site_or_ambiguous_targets_rejected(self, target):
        assert safe_next_path(target) is None


class TestEmailAllowlist:
    @pytest.mark.parametrize('raw, expected', [
        (' Bob@Example.com ', 'bob@example.com'),
        ('P.M.Anderson@gmail.com', 'pmanderson@gmail.com'),
        ('pm.anderson@googlemail.com', 'pmanderson@gmail.com'),
        ('first.last@example.com', 'first.last@example.com'),  # dots only ignored by Gmail
        ('not-an-email', 'not-an-email'),
        (None, ''),
    ])
    def test_normalize_email(self, raw, expected):
        assert auth_service.normalize_email(raw) == expected

    def test_parse_allowed_emails_skips_blanks(self):
        assert auth_service.parse_allowed_emails(' a@x.com, ,B@X.com,') == frozenset({'a@x.com', 'b@x.com'})

    def test_parse_allowed_emails_empty(self):
        assert auth_service.parse_allowed_emails(None) == frozenset()

    def test_authorized_when_verified_and_allowlisted(self):
        assert auth_service.is_authorized(_claims(email='P.M.Anderson@gmail.com'), ALLOWED)

    @pytest.mark.parametrize('claims', [
        _claims(email='stranger@gmail.com'),
        _claims(verified=False),
        _claims(verified='true'),
        {'sub': 'x', 'email': 'homeowner@example.com'},
        {'sub': 'x', 'email_verified': True},
    ])
    def test_not_authorized(self, claims):
        assert not auth_service.is_authorized(claims, ALLOWED)


class TestGetOrCreateUser:
    def test_first_sign_in_creates_household_and_user(self, db):
        user = auth_service.get_or_create_user(_claims(email='New@Example.com', sub='s1', name='New'))
        assert (user.email, user.google_sub, user.name) == ('new@example.com', 's1', 'New')
        assert Household.query.count() == 1
        assert user.household_id == Household.query.one().id

    def test_joins_existing_household(self, db, household):
        user = auth_service.get_or_create_user(_claims(sub='s1'))
        assert user.household_id == household.id
        assert Household.query.count() == 1

    def test_links_pre_google_user_by_email(self, db, household):
        legacy = User(household_id=household.id, email='homeowner@example.com', name='Old')
        db.session.add(legacy)
        db.session.commit()
        user = auth_service.get_or_create_user(_claims(sub='s1'))
        assert user.id == legacy.id
        assert user.google_sub == 's1'

    def test_returning_user_matched_by_sub_and_profile_refreshed(self, db, user):
        returned = auth_service.get_or_create_user(_claims(email='renamed@example.com', name='Renamed'))
        assert returned.id == user.id
        assert (returned.email, returned.name) == ('renamed@example.com', 'Renamed')
        assert User.query.count() == 1


class TestLoginPage:
    def test_renders_google_sign_in(self, client):
        resp = client.get('/login')
        assert resp.status_code == 200
        assert b'Sign in with Google' in resp.data
        assert b'name="password"' not in resp.data

    def test_carries_safe_next_into_sign_in_link(self, client):
        resp = client.get('/login?next=/vendors')
        assert b'/auth/google?next=/vendors' in resp.data

    def test_drops_off_site_next(self, client):
        resp = client.get('/login?next=https://evil.example/')
        assert b'evil.example' not in resp.data

    def test_password_post_no_longer_signs_in(self, client, user):
        resp = client.post('/login', data={'email': user.email, 'password': 'x'})
        assert resp.status_code == 401
        assert client.get('/dashboard').status_code == 302

    def test_signed_in_user_redirected_to_dashboard(self, logged_in_client):
        resp = logged_in_client.get('/login')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/dashboard')


class TestGoogleLogin:
    def test_redirects_to_google_with_pkce_and_account_picker(self, client, google):
        resp = client.get('/auth/google')
        assert resp.status_code == 302
        url = urlsplit(resp.headers['Location'])
        params = parse_qs(url.query)
        assert f'{url.scheme}://{url.netloc}{url.path}' == GOOGLE_METADATA['authorization_endpoint']
        assert params['client_id'] == ['test-client-id']
        assert params['scope'] == ['openid email profile']
        assert params['prompt'] == ['select_account']
        assert params['code_challenge_method'] == ['S256']
        assert params['redirect_uri'] == ['http://localhost/auth/google/callback']
        assert params['state'] and params['nonce']

    def test_configured_redirect_uri_wins(self, app, client, google):
        app.config['GOOGLE_REDIRECT_URI'] = 'https://homebase.example.com/auth/google/callback'
        resp = client.get('/auth/google')
        params = parse_qs(urlsplit(resp.headers['Location']).query)
        assert params['redirect_uri'] == ['https://homebase.example.com/auth/google/callback']


class TestGoogleCallback:
    def test_allowed_account_signs_in_and_is_provisioned(self, client, db, google_returns):
        google_returns(_claims())
        resp = client.get('/auth/google/callback')
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/dashboard')
        assert User.query.filter_by(google_sub='google-sub-homeowner').count() == 1
        assert client.get('/dashboard').status_code == 200

    def test_returns_to_stored_next(self, client, db, google, google_returns):
        client.get('/auth/google?next=/vendors')
        google_returns(_claims())
        resp = client.get('/auth/google/callback')
        assert resp.headers['Location'].endswith('/vendors')

    def test_session_is_permanent(self, client, db, google_returns):
        google_returns(_claims())
        resp = client.get('/auth/google/callback')
        assert 'Expires=' in resp.headers['Set-Cookie']

    @pytest.mark.parametrize('claims', [_claims(email='stranger@gmail.com'), _claims(verified=False)])
    def test_unauthorized_account_denied_without_session(self, client, db, google_returns, claims):
        google_returns(claims)
        resp = client.get('/auth/google/callback')
        assert resp.status_code == 403
        assert b'Access denied' in resp.data
        assert User.query.count() == 0
        assert client.get('/dashboard').status_code == 302

    def test_google_error_returns_to_login(self, client, google, monkeypatch):
        def _raise():
            raise OAuthError(error='access_denied')
        monkeypatch.setattr(google, 'authorize_access_token', _raise)
        resp = client.get('/auth/google/callback?error=access_denied')
        assert resp.status_code == 302
        assert '/login' in resp.headers['Location']

    def test_forged_state_rejected(self, client, db, google):
        resp = client.get('/auth/google/callback?code=abc&state=forged')
        assert resp.status_code == 302
        assert '/login' in resp.headers['Location']
        assert User.query.count() == 0


class TestAccessGuard:
    def test_anonymous_get_redirects_to_login_with_next(self, client):
        resp = client.get('/vendors?sort=name')
        assert resp.status_code == 302
        assert urlsplit(resp.headers['Location']).path == '/login'
        assert parse_qs(urlsplit(resp.headers['Location']).query)['next'] == ['/vendors?sort=name']

    def test_anonymous_unknown_url_does_not_reveal_404(self, client):
        resp = client.get('/no-such-page')
        assert resp.status_code == 302

    def test_anonymous_post_is_401(self, client):
        assert client.post('/vendors/new').status_code == 401

    def test_auth_check_runs_before_csrf(self, app, client):
        app.config['WTF_CSRF_ENABLED'] = True
        assert client.post('/vendors/new').status_code == 401

    def test_login_page_assets_are_public(self, client):
        for filename in ('style.css', 'logo.svg', 'favicon.ico'):
            assert client.get(f'/static/{filename}').status_code == 200

    def test_other_static_files_need_sign_in(self, client):
        assert client.get('/static/anything-else.js').status_code == 302

    def test_removing_email_from_config_revokes_live_session(self, app, logged_in_client):
        app.config['ALLOWED_EMAILS'] = frozenset({'someone-else@example.com'})
        resp = logged_in_client.get('/dashboard')
        assert resp.status_code == 403
        app.config['ALLOWED_EMAILS'] = ALLOWED
        assert logged_in_client.get('/dashboard').status_code == 302

    def test_logout_ends_session(self, logged_in_client):
        resp = logged_in_client.post('/logout')
        assert resp.status_code == 302
        assert logged_in_client.get('/dashboard').status_code == 302


class TestConfig:
    @pytest.fixture
    def production_env(self, monkeypatch):
        monkeypatch.setenv('FLASK_ENV', 'production')
        monkeypatch.setenv('GOOGLE_REDIRECT_URI', 'https://homebase.example.com/auth/google/callback')

    @pytest.mark.parametrize('missing', [
        'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI', 'HOMEBASE_ALLOWED_EMAILS',
    ])
    def test_production_refuses_to_start_without_auth_config(self, production_env, monkeypatch, missing):
        monkeypatch.setenv(missing, '')
        with pytest.raises(RuntimeError, match=missing):
            create_app()

    def test_production_session_cookie_hardening(self, production_env):
        config = create_app().config
        assert config['SESSION_COOKIE_SECURE'] is True
        assert config['SESSION_COOKIE_HTTPONLY'] is True
        assert config['SESSION_COOKIE_SAMESITE'] == 'Lax'
        assert config['PERMANENT_SESSION_LIFETIME'].days == 14
