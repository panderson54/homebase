"""
Flask application factory
"""
import logging
import os
import sqlite3
from logging.handlers import RotatingFileHandler

from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager
from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.engine import Engine

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = 'main.login'

logger = logging.getLogger(__name__)


@event.listens_for(Engine, "connect")
def _set_sqlite_wal(dbapi_conn, _):
    """Enable WAL mode for SQLite to support concurrent Gunicorn workers."""
    if isinstance(dbapi_conn, sqlite3.Connection):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")


def _configure_logging(base_dir):
    """Set up rotating file handlers for app and error logs."""
    log_dir = os.path.join(base_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    fmt = logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s')

    app_handler = RotatingFileHandler(
        os.path.join(log_dir, 'app.log'), maxBytes=5 * 1024 * 1024, backupCount=3
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(fmt)

    error_handler = RotatingFileHandler(
        os.path.join(log_dir, 'error.log'), maxBytes=5 * 1024 * 1024, backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)

    stderr_handler = logging.StreamHandler()
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(fmt)

    root = logging.getLogger()
    if not root.handlers:  # avoid duplicate handlers when create_app is called multiple times (tests)
        root.setLevel(logging.INFO)
        root.addHandler(app_handler)
        root.addHandler(error_handler)
        root.addHandler(stderr_handler)

    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)


def _datefmt(dt, fmt='%b %-d, %Y'):
    """strftime wrapper that handles %-d (no-pad day) on Windows and Linux."""
    if dt is None:
        return ''
    return dt.strftime(fmt.replace('%-d', '{_d_}')).replace('{_d_}', str(dt.day))


def create_app():
    """
    Application factory pattern
    """
    app = Flask(__name__)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(os.path.join(data_dir, 'uploads'), exist_ok=True)
    default_db_url = f'sqlite:///{os.path.join(data_dir, "homebase.db")}'

    _DEV_KEY = 'dev-secret-key-change-this'
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', _DEV_KEY)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', default_db_url)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_DIR'] = os.path.join(data_dir, 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB per request

    _configure_logging(base_dir)

    if app.config['SECRET_KEY'] == _DEV_KEY:
        if os.getenv('FLASK_ENV') == 'production':
            raise RuntimeError(
                'SECRET_KEY must be set in production. '
                'Generate one with: python3 -c "import secrets; print(secrets.token_hex(32))"'
            )
        logger.warning(
            'SECRET_KEY is not set — using insecure dev default. '
            'Add SECRET_KEY to your .env file before deploying.'
        )

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)

    app.jinja_env.filters['datefmt'] = _datefmt

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.routes import main_bp
    app.register_blueprint(main_bp)

    from app import cli
    cli.register(app)

    @app.after_request
    def log_request(response):
        if not request.path.startswith('/static'):
            level = logging.WARNING if response.status_code >= 400 else logging.INFO
            logging.getLogger('app.request').log(
                level, '%s %s %d', request.method, request.path, response.status_code
            )
        return response

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception('Unhandled exception on %s %s', request.method, request.path)
        return 'Internal Server Error', 500

    return app
