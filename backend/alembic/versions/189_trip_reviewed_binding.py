"""Reviewed placeholder identity for immutable trips; no binding activation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '189_trip_reviewed_binding'
down_revision = '188_callrail_media_cache'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('fleet_trip_snapshots', 'verified_vin', existing_type=sa.String(17), nullable=True)
    op.add_column('fleet_trip_snapshots', sa.Column('dashboard_binding_id', postgresql.UUID(as_uuid=True)))
    op.add_column('fleet_trip_snapshots', sa.Column('source_company_id', sa.String(120)))
    op.add_column('fleet_trip_snapshots', sa.Column('source_company_label', sa.String(255)))
    op.add_column('fleet_trip_snapshots', sa.Column('source_vin_state', sa.String(30)))
    op.create_foreign_key('fk_trip_dashboard_binding', 'fleet_trip_snapshots', 'dashboard_vehicle_bindings', ['tenant_id', 'vehicle_id', 'fleet_membership_id', 'dashboard_binding_id'], ['tenant_id', 'vehicle_id', 'fleet_membership_id', 'id'])
    op.create_check_constraint('ck_trip_identity_xor', 'fleet_trip_snapshots', "(verified_vin IS NOT NULL AND dashboard_binding_id IS NULL AND source_company_id IS NULL AND source_company_label IS NULL AND source_vin_state IS NULL) OR (verified_vin IS NULL AND dashboard_binding_id IS NOT NULL AND source_company_id = 'KT8934277' AND source_company_id IS NOT NULL AND source_company_label = '77 CARGO LLC' AND source_company_label IS NOT NULL AND provider_vehicle_id = '5981300' AND source_vin_state IN ('not_displayed', 'explicitly_empty') AND source_vin_state IS NOT NULL)")


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM fleet_trip_snapshots WHERE dashboard_binding_id IS NOT NULL LIMIT 1')).first():
        raise RuntimeError('Bound trip history exists; preserve schema and guarded readers')
    op.drop_constraint('ck_trip_identity_xor', 'fleet_trip_snapshots', type_='check')
    op.drop_constraint('fk_trip_dashboard_binding', 'fleet_trip_snapshots', type_='foreignkey')
    for name in ('source_vin_state', 'source_company_label', 'source_company_id', 'dashboard_binding_id'):
        op.drop_column('fleet_trip_snapshots', name)
    op.alter_column('fleet_trip_snapshots', 'verified_vin', existing_type=sa.String(17), nullable=False)
