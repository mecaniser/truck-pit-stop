"""Immutable driver observations and local assignment invalidation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "163_fleet_driver_records"
down_revision = "162_fleet_diagnostic_captures"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fleet_driver_directory_captures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("fleet_customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_company_id", sa.String(120), nullable=False),
        sa.Column("source_company_label", sa.String(255), nullable=False),
        sa.Column("source_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("assignments", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "fleet_customer_id",
            "source_sha256",
            name="uq_driver_directory_source",
        ),
    )
    op.create_index(
        "ix_fleet_driver_directory_captures_id",
        "fleet_driver_directory_captures",
        ["id"],
    )
    op.create_index(
        "ix_driver_directory_customer_read",
        "fleet_driver_directory_captures",
        ["tenant_id", "fleet_customer_id", "source_read_at"],
    )
    op.add_column(
        "vehicles",
        sa.Column(
            "driver_assignment_revision",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "vehicles",
        sa.Column("driver_assignment_changed_at", sa.DateTime(timezone=True)),
    )
    op.execute("""
        CREATE FUNCTION advance_vehicle_driver_assignment_revision() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.driver_name IS DISTINCT FROM OLD.driver_name
             OR NEW.driver_phone IS DISTINCT FROM OLD.driver_phone THEN
            NEW.driver_assignment_revision := OLD.driver_assignment_revision + 1;
            NEW.driver_assignment_changed_at := clock_timestamp();
          ELSE
            NEW.driver_assignment_revision := OLD.driver_assignment_revision;
            NEW.driver_assignment_changed_at := OLD.driver_assignment_changed_at;
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER trg_vehicle_driver_assignment_revision
        BEFORE UPDATE ON vehicles FOR EACH ROW
        EXECUTE FUNCTION advance_vehicle_driver_assignment_revision()
    """)
    op.create_table(
        "fleet_driver_record_captures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("vehicle_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_membership_id", UUID(as_uuid=True), nullable=False),
        sa.Column("verified_vin", sa.String(17), nullable=False),
        sa.Column("provider_vehicle_id", sa.String(120), nullable=False),
        sa.Column("provider_driver_id", sa.String(120), nullable=False),
        sa.Column("driver_name", sa.String(160), nullable=False),
        sa.Column("local_driver_name", sa.String(160)),
        sa.Column("local_driver_phone", sa.String(20)),
        sa.Column("driver_assignment_revision", sa.Integer(), nullable=False),
        sa.Column("source_company_id", sa.String(120), nullable=False),
        sa.Column("source_company_label", sa.String(255), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("source_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "captured_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("client_request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "client_request_id", name="uq_driver_record_request"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "vehicle_id", "fleet_customer_id", "fleet_membership_id"],
            [
                "fleet_memberships.tenant_id",
                "fleet_memberships.vehicle_id",
                "fleet_memberships.fleet_customer_id",
                "fleet_memberships.id",
            ],
        ),
        sa.CheckConstraint(
            "source = 'motive_dashboard'", name="ck_driver_record_source"
        ),
        sa.CheckConstraint(
            "source_read_at <= captured_at", name="ck_driver_record_read_time"
        ),
        sa.CheckConstraint(
            "driver_assignment_revision >= 0",
            name="ck_driver_record_assignment_revision",
        ),
    )
    op.create_index(
        "ix_fleet_driver_record_captures_id", "fleet_driver_record_captures", ["id"]
    )
    op.create_index(
        "ix_driver_record_vehicle_read",
        "fleet_driver_record_captures",
        ["tenant_id", "vehicle_id", "source_read_at"],
    )
    op.create_index(
        "ix_driver_record_provider",
        "fleet_driver_record_captures",
        ["tenant_id", "source_company_id", "provider_driver_id"],
    )


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM fleet_driver_record_captures) OR EXISTS (SELECT 1 FROM fleet_driver_directory_captures) THEN RAISE EXCEPTION 'Retain revision 163: driver observations exist'; END IF; END $$"
    )
    op.drop_table("fleet_driver_record_captures")
    op.drop_table("fleet_driver_directory_captures")
    op.execute("DROP TRIGGER trg_vehicle_driver_assignment_revision ON vehicles")
    op.execute("DROP FUNCTION advance_vehicle_driver_assignment_revision()")
    op.drop_column("vehicles", "driver_assignment_changed_at")
    op.drop_column("vehicles", "driver_assignment_revision")
