"""link vendor quotes to appliances and zones

Revision ID: 9c9c036306c6
Revises: eff0d1a0689d
Create Date: 2026-10-05 20:45:34.115488

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c9c036306c6'
down_revision = 'eff0d1a0689d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vendor_quotes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('appliance_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('zone_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_vendor_quotes_appliance_id'), ['appliance_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_vendor_quotes_zone_id'), ['zone_id'], unique=False)
        batch_op.create_foreign_key('fk_vendor_quotes_appliance_id_appliances', 'appliances', ['appliance_id'], ['id'])
        batch_op.create_foreign_key('fk_vendor_quotes_zone_id_zones', 'zones', ['zone_id'], ['id'])
        batch_op.create_check_constraint('ck_vendor_quote_appliance_or_zone', 'appliance_id IS NULL OR zone_id IS NULL')


def downgrade():
    with op.batch_alter_table('vendor_quotes', schema=None) as batch_op:
        batch_op.drop_constraint('ck_vendor_quote_appliance_or_zone', type_='check')
        batch_op.drop_constraint('fk_vendor_quotes_zone_id_zones', type_='foreignkey')
        batch_op.drop_constraint('fk_vendor_quotes_appliance_id_appliances', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_vendor_quotes_zone_id'))
        batch_op.drop_index(batch_op.f('ix_vendor_quotes_appliance_id'))
        batch_op.drop_column('zone_id')
        batch_op.drop_column('appliance_id')
