"""Gateway auth for the shared Google-SSO deployment (stack lives in ledger_finance/deploy/).
AUTH_MODE=password (default) keeps the built-in login; AUTH_MODE=proxy trusts oauth2-proxy's
email header only on requests that also carry the per-app secret Caddy injects, and the
`users` table stays this app's own allowlist on top of the gateway's."""
import hmac
import logging
import os

from flask import abort, current_app, request
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix

EMAIL_HEADER = 'X-Forwarded-Email'
SECRET_HEADER = 'X-Proxy-Secret'
AUTH_MODES = ('password', 'proxy')
SIGN_OUT_URL = '/oauth2/sign_out'

logger = logging.getLogger(__name__)


def is_proxy_mode():
    return current_app.config.get('AUTH_MODE') == 'proxy'


def init_app(app):
    mode = os.getenv('AUTH_MODE', 'password').strip().lower()
    if mode not in AUTH_MODES:
        raise RuntimeError(f'AUTH_MODE must be one of {AUTH_MODES}, got {mode!r}')
    app.config['AUTH_MODE'] = mode
    # Distinct from other apps on the same domain so their sessions never collide.
    app.config['SESSION_COOKIE_NAME'] = 'homebase_session'
    if mode != 'proxy':
        return

    secret = os.getenv('AUTH_PROXY_SECRET', '')
    if not secret:
        raise RuntimeError('AUTH_MODE=proxy requires AUTH_PROXY_SECRET (must match the gateway).')
    app.config.update(AUTH_PROXY_SECRET=secret, SESSION_COOKIE_SECURE=True)
    # Exactly one trusted hop (Caddy): lets redirects use the public https host.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.before_request(_require_gateway_identity)


def load_user_from_gateway(req, user_model):
    if not is_proxy_mode():
        return None
    email = req.headers.get(EMAIL_HEADER, '').strip().lower()
    return user_model.query.filter_by(email=email).first() if email else None


def _require_gateway_identity():
    supplied = request.headers.get(SECRET_HEADER, '')
    if not hmac.compare_digest(supplied.encode(), current_app.config['AUTH_PROXY_SECRET'].encode()):
        logger.warning('Rejected %s %s: missing or wrong gateway secret', request.method, request.path)
        abort(401)

    if not current_user.is_authenticated:
        email = request.headers.get(EMAIL_HEADER, '').strip().lower()
        logger.warning('Rejected %s %s for %s: no matching Homebase user',
                       request.method, request.path, email or '<no email>')
        abort(403, description=(
            'This Google account is signed in but is not linked to a Homebase user. '
            'Ask the admin to run `flask create-user --no-password` for it.'
        ))
