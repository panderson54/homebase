"""add vendors and generalize service records

Revision ID: 3bfdedad2d65
Revises: f1e7ec9fb8a2
Create Date: 2026-08-27 16:37:09.132284

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3bfdedad2d65'
down_revision = 'f1e7ec9fb8a2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('vendors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('household_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('vendor_type', sa.String(length=80), nullable=False),
    sa.Column('contact_name', sa.String(length=120), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('website', sa.String(length=500), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # household_id/vendor_id must be backfilled (from the still-present appliance_id
    # and vendor columns) before either can be tightened, so add them nullable first.
    with op.batch_alter_table('service_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('household_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('vendor_id', sa.Integer(), nullable=True))
        batch_op.alter_column('appliance_id', existing_type=sa.Integer(), nullable=True)

    # Every distinct historical vendor name becomes a real (editable) Vendor row,
    # defaulted to type 'other' since free text never carried a type.
    op.execute(
        "INSERT INTO vendors (household_id, name, vendor_type, created_at) "
        "SELECT DISTINCT a.household_id, sr.vendor, 'other', datetime('now') "
        "FROM service_records sr JOIN appliances a ON a.id = sr.appliance_id "
        "WHERE sr.vendor IS NOT NULL"
    )
    op.execute(
        "UPDATE service_records SET vendor_id = ("
        "  SELECT v.id FROM vendors v JOIN appliances a ON a.household_id = v.household_id"
        "  WHERE a.id = service_records.appliance_id AND v.name = service_records.vendor"
        ") WHERE service_records.vendor IS NOT NULL"
    )
    op.execute(
        "UPDATE service_records SET household_id = "
        "(SELECT household_id FROM appliances WHERE appliances.id = service_records.appliance_id) "
        "WHERE service_records.appliance_id IS NOT NULL"
    )

    with op.batch_alter_table('service_records', schema=None) as batch_op:
        batch_op.alter_column('household_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            'fk_service_records_household_id_households', 'households', ['household_id'], ['id']
        )
        batch_op.create_foreign_key(
            'fk_service_records_vendor_id_vendors', 'vendors', ['vendor_id'], ['id']
        )
        batch_op.drop_column('vendor')

    # Widen the doc_type/entity_type CHECK constraints. Autogenerate doesn't surface
    # these (the reflected VARCHAR length doesn't grow — the longest existing member,
    # 'inspection_report'/'appliance', is already longer than the new ones), so the
    # rewrite has to be forced explicitly, same technique as the previous migration.
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.alter_column('doc_type',
               existing_type=sa.VARCHAR(length=18),
               type_=sa.Enum(
                   'photo', 'manual', 'receipt', 'floor_plan', 'inspection_report',
                   'quote', 'invoice', 'other', name='documenttype', native_enum=False,
               ),
               existing_nullable=False)

    with op.batch_alter_table('document_links', schema=None) as batch_op:
        batch_op.alter_column('entity_type',
               existing_type=sa.VARCHAR(length=9),
               type_=sa.Enum('appliance', 'home', 'vendor', name='documententitytype', native_enum=False),
               existing_nullable=False)


def downgrade():
    # Lossy: any service_record with no appliance_id (a vendor-only visit) has no
    # equivalent in the old appliance-required schema and will fail the NOT NULL
    # backfill below — this reflects a real loss of information, not a bug.
    with op.batch_alter_table('document_links', schema=None) as batch_op:
        batch_op.alter_column('entity_type',
               existing_type=sa.Enum('appliance', 'home', 'vendor', name='documententitytype', native_enum=False),
               type_=sa.VARCHAR(length=9),
               existing_nullable=False)

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.alter_column('doc_type',
               existing_type=sa.Enum(
                   'photo', 'manual', 'receipt', 'floor_plan', 'inspection_report',
                   'quote', 'invoice', 'other', name='documenttype', native_enum=False,
               ),
               type_=sa.VARCHAR(length=18),
               existing_nullable=False)

    with op.batch_alter_table('service_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('vendor', sa.VARCHAR(length=200), nullable=True))

    op.execute(
        "UPDATE service_records SET vendor = "
        "(SELECT name FROM vendors WHERE vendors.id = service_records.vendor_id) "
        "WHERE service_records.vendor_id IS NOT NULL"
    )

    with op.batch_alter_table('service_records', schema=None) as batch_op:
        batch_op.alter_column('appliance_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column('vendor_id')
        batch_op.drop_column('household_id')

    op.drop_table('vendors')
