"""add zone to appliances (also merges the two open heads)

Revision ID: a8d3f1c2b7e4
Revises: 9c9c036306c6, ca4fb53427d2
Create Date: 2026-10-06 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8d3f1c2b7e4'
down_revision = ('9c9c036306c6', 'ca4fb53427d2')
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('appliances', schema=None) as batch_op:
        batch_op.add_column(sa.Column('zone_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_appliances_zone_id_zones', 'zones', ['zone_id'], ['id'])


def downgrade():
    with op.batch_alter_table('appliances', schema=None) as batch_op:
        batch_op.drop_constraint('fk_appliances_zone_id_zones', type_='foreignkey')
        batch_op.drop_column('zone_id')
