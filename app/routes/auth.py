import logging

from authlib.integrations.base_client import OAuthError
from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import auth_service
from app.routes import main_bp
from app.routes.helpers import safe_next_path

logger = logging.getLogger(__name__)

_NEXT_SESSION_KEY = 'login_next'


@main_bp.route('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('auth/login.html', next_path=safe_next_path(request.args.get('next')))


@main_bp.route('/auth/google')
def google_login():
    session[_NEXT_SESSION_KEY] = safe_next_path(request.args.get('next'))
    redirect_uri = current_app.config['GOOGLE_REDIRECT_URI'] or url_for('main.google_callback', _external=True)
    return current_app.extensions['google_oauth'].authorize_redirect(redirect_uri, prompt='select_account')


@main_bp.route('/auth/google/callback')
def google_callback():
    try:
        token = current_app.extensions['google_oauth'].authorize_access_token()
    except OAuthError as e:
        logger.warning('Google sign-in failed: %s', e.error)
        flash('Google sign-in failed. Please try again.', 'danger')
        return redirect(url_for('main.login'))

    claims = token.get('userinfo') or {}
    next_path = session.pop(_NEXT_SESSION_KEY, None)
    if not auth_service.is_authorized(claims, current_app.config['ALLOWED_EMAILS']):
        logger.warning('Denied Google sign-in for %s', claims.get('email'))
        session.clear()
        return render_template('auth/forbidden.html'), 403

    user = auth_service.get_or_create_user(claims)
    session.clear()  # fresh session on sign-in: nothing set before auth carries over
    session.permanent = True
    login_user(user)
    return redirect(next_path or url_for('main.dashboard'))


@main_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('main.login'))
