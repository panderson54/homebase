from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / 'migrations'


def test_migrations_have_a_single_head():
    # entrypoint.sh runs a bare `flask db upgrade`, which refuses to start the app on multiple heads.
    config = Config()
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1
