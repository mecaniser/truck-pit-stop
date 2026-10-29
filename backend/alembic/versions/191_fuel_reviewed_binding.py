"""Reviewed placeholder identity for immutable daily fuel; no binding activation."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "191_fuel_reviewed_binding"
down_revision = "190_messages_contact_context"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "fleet_daily_fuel_snapshots",
        "verified_vin",
        existing_type=sa.String(17),
        nullable=True,
    )
    op.add_column(
        "fleet_daily_fuel_snapshots",
        sa.Column("dashboard_binding_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "fleet_daily_fuel_snapshots", sa.Column("source_company_label", sa.String(255))
    )
    op.add_column(
        "fleet_daily_fuel_snapshots", sa.Column("source_vin_state", sa.String(30))
    )
    op.create_foreign_key(
        "fk_fuel_dashboard_binding",
        "fleet_daily_fuel_snapshots",
        "dashboard_vehicle_bindings",
        ["tenant_id", "vehicle_id", "fleet_membership_id", "dashboard_binding_id"],
        ["tenant_id", "vehicle_id", "fleet_membership_id", "id"],
    )
    op.create_check_constraint(
        "ck_fuel_identity_xor",
        "fleet_daily_fuel_snapshots",
        "(verified_vin IS NOT NULL AND dashboard_binding_id IS NULL AND source_company_label IS NULL AND source_vin_state IS NULL) OR (verified_vin IS NULL AND dashboard_binding_id IS NOT NULL AND provider_company_id = 'KT8934277' AND source_company_label = '77 CARGO LLC' AND source_company_label IS NOT NULL AND provider_vehicle_id = '5981300' AND source_vin_state IN ('not_displayed', 'explicitly_empty') AND source_vin_state IS NOT NULL)",
    )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM fleet_daily_fuel_snapshots WHERE dashboard_binding_id IS NOT NULL LIMIT 1"
            )
        )
        .first()
    ):
        raise RuntimeError(
            "Bound fuel history exists; preserve schema and guarded readers"
        )
    op.drop_constraint(
        "ck_fuel_identity_xor", "fleet_daily_fuel_snapshots", type_="check"
    )
    op.drop_constraint(
        "fk_fuel_dashboard_binding", "fleet_daily_fuel_snapshots", type_="foreignkey"
    )
    for name in ("source_vin_state", "source_company_label", "dashboard_binding_id"):
        op.drop_column("fleet_daily_fuel_snapshots", name)
    op.alter_column(
        "fleet_daily_fuel_snapshots",
        "verified_vin",
        existing_type=sa.String(17),
        nullable=False,
    )
