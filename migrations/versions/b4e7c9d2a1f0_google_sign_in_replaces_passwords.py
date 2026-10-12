"""google sign-in replaces passwords

Revision ID: b4e7c9d2a1f0
Revises: a8d3f1c2b7e4
Create Date: 2026-10-12 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4e7c9d2a1f0'
down_revision = 'a8d3f1c2b7e4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('google_sub', sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint('uq_users_google_sub', ['google_sub'])
        batch_op.drop_column('password_hash')


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        # Restored empty, so no password matches until one is set again.
        batch_op.add_column(sa.Column('password_hash', sa.String(length=255), nullable=False, server_default=''))
        batch_op.drop_constraint('uq_users_google_sub', type_='unique')
        batch_op.drop_column('google_sub')
