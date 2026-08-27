"""add home profile fields and generalize documents

Revision ID: f1e7ec9fb8a2
Revises: eaa7c58619a6
Create Date: 2026-08-27 15:21:14.008215

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1e7ec9fb8a2'
down_revision = 'eaa7c58619a6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('document_links',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('entity_type', sa.Enum('appliance', 'home', name='documententitytype', native_enum=False), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'entity_type', 'entity_id', name='uq_document_link')
    )
    with op.batch_alter_table('document_links', schema=None) as batch_op:
        batch_op.create_index('ix_document_links_entity', ['entity_type', 'entity_id'], unique=False)

    # Every existing document was implicitly linked to exactly one appliance —
    # make that explicit as a document_links row before appliance_id goes away.
    op.execute(
        "INSERT INTO document_links (document_id, entity_type, entity_id) "
        "SELECT id, 'appliance', appliance_id FROM documents WHERE appliance_id IS NOT NULL"
    )

    # household_id must be backfilled from the (still-present) appliance_id before
    # it can be made NOT NULL, so add it nullable first in its own batch step.
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('household_id', sa.Integer(), nullable=True))
        batch_op.alter_column('doc_type',
               existing_type=sa.VARCHAR(length=7),
               type_=sa.Enum('photo', 'manual', 'receipt', 'floor_plan', 'inspection_report', 'other', name='documenttype', native_enum=False),
               existing_nullable=False)

    op.execute(
        "UPDATE documents SET household_id = "
        "(SELECT household_id FROM appliances WHERE appliances.id = documents.appliance_id)"
    )

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.alter_column('household_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_documents_household_id_households', 'households', ['household_id'], ['id'])
        batch_op.drop_column('appliance_id')

    with op.batch_alter_table('households', schema=None) as batch_op:
        batch_op.add_column(sa.Column('address', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('square_footage', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('year_built', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('notes', sa.Text(), nullable=True))


def downgrade():
    # Lossy: any document linked to the home (or to more than one appliance) has no
    # equivalent in the old single-appliance_id schema and will fail the NOT NULL
    # backfill below — this reflects a real loss of information, not a bug.
    with op.batch_alter_table('households', schema=None) as batch_op:
        batch_op.drop_column('notes')
        batch_op.drop_column('year_built')
        batch_op.drop_column('square_footage')
        batch_op.drop_column('address')

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('appliance_id', sa.INTEGER(), nullable=True))
        batch_op.alter_column('doc_type',
               existing_type=sa.Enum('photo', 'manual', 'receipt', 'floor_plan', 'inspection_report', 'other', name='documenttype', native_enum=False),
               type_=sa.VARCHAR(length=7),
               existing_nullable=False)

    op.execute(
        "UPDATE documents SET appliance_id = "
        "(SELECT entity_id FROM document_links "
        " WHERE document_links.document_id = documents.id AND document_links.entity_type = 'appliance')"
    )

    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.alter_column('appliance_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_documents_appliance_id_appliances', 'appliances', ['appliance_id'], ['id'])
        batch_op.drop_column('household_id')

    with op.batch_alter_table('document_links', schema=None) as batch_op:
        batch_op.drop_index('ix_document_links_entity')

    op.drop_table('document_links')
