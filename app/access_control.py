"""Deny-by-default request guard: every request needs a signed-in user whose email is
still on the server-configured allowlist, except the few endpoints signing in needs."""
import logging

from flask import abort, current_app, redirect, render_template, request, session, url_for
from flask_login import current_user, logout_user

from app.auth_service import is_email_allowed

logger = logging.getLogger(__name__)

PUBLIC_ENDPOINTS = frozenset({'main.login', 'main.google_login', 'main.google_callback'})
# Only what the login page itself loads; every other static file stays private.
PUBLIC_STATIC_FILES = frozenset({'style.css', 'logo.svg', 'favicon.ico'})


def _is_public_request():
    if request.endpoint in PUBLIC_ENDPOINTS:
        return True
    return request.endpoint == 'static' and (request.view_args or {}).get('filename') in PUBLIC_STATIC_FILES


def require_authorized_user():
    # Runs before routing errors are raised, so unknown URLs (endpoint None) are
    # denied too — an anonymous client can't probe which routes exist.
    if _is_public_request():
        return None

    if not current_user.is_authenticated:
        if request.method in ('GET', 'HEAD'):
            next_path = request.full_path if request.query_string else request.path
            return redirect(url_for('main.login', next=next_path))
        abort(401)

    # Re-checked on every request so removing an address from the config (and
    # restarting) locks that user out even with a still-valid session cookie.
    if not is_email_allowed(current_user.email, current_app.config['ALLOWED_EMAILS']):
        logger.warning('Revoking session for %s: no longer on the allowlist', current_user.email)
        logout_user()
        session.clear()
        return render_template('auth/forbidden.html'), 403

    return None


def register(app):
    app.before_request(require_authorized_user)
