"""AUTH_MODE=proxy: only requests that come through the Google-SSO gateway, for a
Google account linked to a Homebase user, get in."""
import pytest

from app import create_app
from app import db as _db
from app.proxy_auth import EMAIL_HEADER, SECRET_HEADER

SECRET = 'gateway-secret'


@pytest.fixture
def proxy_app(monkeypatch):
    monkeypatch.setenv('AUTH_MODE', 'proxy')
    monkeypatch.setenv('AUTH_PROXY_SECRET', SECRET)
    flask_app = create_app()
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def proxy_client(proxy_app):
    return proxy_app.test_client()


@pytest.fixture
def linked_users(proxy_app):
    from app.models import Household, User
    household = Household(name='Test Home')
    _db.session.add(household)
    _db.session.flush()
    users = [
        User(household_id=household.id, email=email, name=name, password_hash='unused')
        for email, name in (('owner@gmail.com', 'Owner'), ('partner@gmail.com', 'Partner'))
    ]
    _db.session.add_all(users)
    _db.session.commit()
    return users


def _headers(email='owner@gmail.com', secret=SECRET):
    return {EMAIL_HEADER: email, SECRET_HEADER: secret}


class TestStartupConfig:
    def test_default_mode_is_password(self, app):
        assert app.config['AUTH_MODE'] == 'password'

    def test_session_cookie_is_app_specific(self, app):
        assert app.config['SESSION_COOKIE_NAME'] == 'homebase_session'

    def test_unknown_mode_raises(self, monkeypatch):
        monkeypatch.setenv('AUTH_MODE', 'google')
        with pytest.raises(RuntimeError, match='AUTH_MODE'):
            create_app()

    def test_proxy_mode_without_secret_raises(self, monkeypatch):
        monkeypatch.setenv('AUTH_MODE', 'proxy')
        monkeypatch.delenv('AUTH_PROXY_SECRET', raising=False)
        with pytest.raises(RuntimeError, match='AUTH_PROXY_SECRET'):
            create_app()


class TestGatewayCheck:
    def test_linked_account_through_gateway_succeeds(self, proxy_client, linked_users):
        resp = proxy_client.get('/dashboard', headers=_headers('Owner@Gmail.com'))
        assert resp.status_code == 200
        assert b'Owner' in resp.data

    def test_missing_secret_is_401_even_with_valid_email(self, proxy_client, linked_users):
        assert proxy_client.get('/dashboard', headers={EMAIL_HEADER: 'owner@gmail.com'}).status_code == 401

    def test_wrong_secret_is_401(self, proxy_client, linked_users):
        assert proxy_client.get('/dashboard', headers=_headers(secret='guess')).status_code == 401

    def test_unlinked_account_is_403(self, proxy_client, linked_users):
        resp = proxy_client.get('/dashboard', headers=_headers('stranger@gmail.com'))
        assert resp.status_code == 403
        assert b'not linked to a Homebase user' in resp.data

    def test_missing_email_is_403(self, proxy_client, linked_users):
        assert proxy_client.get('/dashboard', headers={SECRET_HEADER: SECRET}).status_code == 403

    def test_stale_session_cannot_override_gateway_identity(self, proxy_client, linked_users):
        owner, partner = linked_users
        with proxy_client.session_transaction() as sess:
            sess['_user_id'] = str(owner.id)
        resp = proxy_client.get('/dashboard', headers=_headers(partner.email))
        assert b'Partner' in resp.data
        assert b'>Owner<' not in resp.data

    def test_logout_signs_out_of_gateway(self, proxy_client, linked_users):
        resp = proxy_client.post('/logout', headers=_headers())
        assert resp.status_code == 302
        assert resp.headers['Location'].endswith('/oauth2/sign_out')


class TestCreateUserNoPassword:
    def test_creates_user_without_prompting(self, app, db):
        from app.models import User
        result = app.test_cli_runner().invoke(
            args=['create-user', '--email', 'New@Gmail.com', '--name', 'New', '--no-password'],
        )
        assert result.exit_code == 0, result.output
        user = User.query.filter_by(email='new@gmail.com').one()
        assert user.password_hash
