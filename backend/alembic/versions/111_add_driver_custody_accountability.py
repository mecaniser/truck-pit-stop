"""add driver profiles, equipment custody, and accountability history

Revision ID: 111_driver_accountability
Revises: 110_workos_identity_mapping
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "111_driver_accountability"
down_revision = "110_workos_identity_mapping"
branch_labels = None
depends_on = None


def _base_columns():
    return (
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    # Local compatibility role for a WorkOS-backed driver User projection.
    # Driver authorization still comes from WorkOS permissions plus record
    # ownership checks, never from this enum alone.
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'driver'")
    op.execute("ALTER TYPE incidentstatus ADD VALUE IF NOT EXISTS 'voided'")

    op.create_table(
        "driver_profiles",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("employer_customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("employee_number", sa.String(80), nullable=True),
        sa.Column("license_number", sa.String(80), nullable=True),
        sa.Column("license_state", sa.String(2), nullable=True),
        sa.Column("license_expires_on", sa.Date(), nullable=True),
        sa.Column("employment_status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("hired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_base_columns(),
        sa.CheckConstraint(
            "employment_status IN ('active', 'inactive')",
            name="ck_driver_profiles_employment_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["employer_customer_id"], ["customers.id"]),
        sa.UniqueConstraint("user_id", name="uq_driver_profiles_user_id"),
    )
    for name, columns in (
        ("ix_driver_profiles_tenant_id", ["tenant_id"]),
        ("ix_driver_profiles_user_id", ["user_id"]),
        ("ix_driver_profiles_employer_customer_id", ["employer_customer_id"]),
        ("ix_driver_profiles_tenant_status", ["tenant_id", "employment_status"]),
    ):
        op.create_index(name, "driver_profiles", columns)
    op.create_index(
        "uq_driver_profiles_active_employee_number",
        "driver_profiles",
        ["tenant_id", "employee_number"],
        unique=True,
        postgresql_where=sa.text(
            "employee_number IS NOT NULL AND employment_status = 'active' AND deleted_at IS NULL"
        ),
    )

    op.create_table(
        "fleet_trailers",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vin", sa.String(17), nullable=True),
        sa.Column("unit_number", sa.String(50), nullable=True),
        sa.Column("make", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("license_plate", sa.String(20), nullable=True),
        sa.Column("body_type", sa.String(80), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        *_base_columns(),
        sa.CheckConstraint(
            "status IN ('active', 'yard', 'out_of_service', 'retired')",
            name="ck_fleet_trailers_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["owner_customer_id"], ["customers.id"]),
    )
    for name, columns in (
        ("ix_fleet_trailers_tenant_id", ["tenant_id"]),
        ("ix_fleet_trailers_owner_customer_id", ["owner_customer_id"]),
        ("ix_fleet_trailers_vin", ["vin"]),
        ("ix_fleet_trailers_unit_number", ["unit_number"]),
        ("ix_fleet_trailers_license_plate", ["license_plate"]),
    ):
        op.create_index(name, "fleet_trailers", columns)
    op.execute(
        "CREATE INDEX ix_fleet_trailers_tenant_normalized_vin "
        "ON fleet_trailers (tenant_id, upper(vin)) "
        "WHERE vin IS NOT NULL AND length(trim(vin)) = 17 AND deleted_at IS NULL"
    )

    op.create_table(
        "equipment_custody_sessions",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("released_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="assigned"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatch_reference", sa.String(120), nullable=True),
        sa.Column("handoff_notes", sa.Text(), nullable=True),
        *_base_columns(),
        sa.CheckConstraint(
            "status IN ('assigned', 'active', 'closed', 'cancelled')",
            name="ck_equipment_custody_sessions_status",
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at >= starts_at",
            name="ck_equipment_custody_sessions_dates",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["driver_id"], ["driver_profiles.id"]),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["released_by_user_id"], ["users.id"]),
    )
    for name, columns in (
        ("ix_equipment_custody_sessions_tenant_id", ["tenant_id"]),
        ("ix_equipment_custody_sessions_driver_id", ["driver_id"]),
        ("ix_equipment_custody_sessions_status", ["status"]),
        ("ix_equipment_custody_sessions_starts_at", ["starts_at"]),
        ("ix_equipment_custody_sessions_ends_at", ["ends_at"]),
        (
            "ix_equipment_custody_driver_timeline",
            ["tenant_id", "driver_id", "starts_at", "ends_at"],
        ),
    ):
        op.create_index(name, "equipment_custody_sessions", columns)

    op.create_table(
        "equipment_custody_assets",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("custody_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trailer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("equipment_role", sa.String(24), nullable=False),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_odometer", sa.Integer(), nullable=True),
        sa.Column("end_odometer", sa.Integer(), nullable=True),
        sa.Column("checkout_condition", sa.Text(), nullable=True),
        sa.Column("checkin_condition", sa.Text(), nullable=True),
        *_base_columns(),
        sa.CheckConstraint(
            "(vehicle_id IS NOT NULL AND trailer_id IS NULL) OR "
            "(vehicle_id IS NULL AND trailer_id IS NOT NULL)",
            name="ck_equipment_custody_assets_exactly_one_asset",
        ),
        sa.CheckConstraint(
            "equipment_role IN ('power_unit', 'trailer')",
            name="ck_equipment_custody_assets_role",
        ),
        sa.CheckConstraint(
            "released_at IS NULL OR released_at >= attached_at",
            name="ck_equipment_custody_assets_dates",
        ),
        sa.CheckConstraint(
            "start_odometer IS NULL OR start_odometer >= 0",
            name="ck_equipment_custody_assets_start_odometer",
        ),
        sa.CheckConstraint(
            "end_odometer IS NULL OR end_odometer >= 0",
            name="ck_equipment_custody_assets_end_odometer",
        ),
        sa.ForeignKeyConstraint(
            ["custody_session_id"], ["equipment_custody_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"]),
        sa.ForeignKeyConstraint(["trailer_id"], ["fleet_trailers.id"]),
    )
    for name, columns in (
        ("ix_equipment_custody_assets_tenant_id", ["tenant_id"]),
        ("ix_equipment_custody_assets_custody_session_id", ["custody_session_id"]),
        ("ix_equipment_custody_assets_vehicle_id", ["vehicle_id"]),
        ("ix_equipment_custody_assets_trailer_id", ["trailer_id"]),
        ("ix_equipment_custody_assets_released_at", ["released_at"]),
    ):
        op.create_index(name, "equipment_custody_assets", columns)
    op.create_index(
        "uq_equipment_custody_active_vehicle",
        "equipment_custody_assets",
        ["vehicle_id"],
        unique=True,
        postgresql_where=sa.text(
            "vehicle_id IS NOT NULL AND released_at IS NULL AND deleted_at IS NULL"
        ),
    )
    op.create_index(
        "uq_equipment_custody_active_trailer",
        "equipment_custody_assets",
        ["trailer_id"],
        unique=True,
        postgresql_where=sa.text(
            "trailer_id IS NOT NULL AND released_at IS NULL AND deleted_at IS NULL"
        ),
    )

    # Extend existing maintenance records additively. Existing weekly
    # inspections and incidents retain their current vehicle/actor history.
    for name, column in (
        ("trailer_id", sa.Column("trailer_id", postgresql.UUID(as_uuid=True), nullable=True)),
        (
            "custody_session_id",
            sa.Column("custody_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        ),
        ("driver_id", sa.Column("driver_id", postgresql.UUID(as_uuid=True), nullable=True)),
        (
            "inspection_type",
            sa.Column("inspection_type", sa.String(24), nullable=False, server_default="weekly"),
        ),
        ("attested_at", sa.Column("attested_at", sa.DateTime(timezone=True), nullable=True)),
        ("attestation_version", sa.Column("attestation_version", sa.String(32), nullable=True)),
        ("attested_name", sa.Column("attested_name", sa.String(200), nullable=True)),
    ):
        op.add_column("fleet_inspections", column)
    op.create_foreign_key("fk_fleet_inspections_trailer", "fleet_inspections", "fleet_trailers", ["trailer_id"], ["id"])
    op.create_foreign_key(
        "fk_fleet_inspections_custody",
        "fleet_inspections",
        "equipment_custody_sessions",
        ["custody_session_id"],
        ["id"],
    )
    op.create_foreign_key("fk_fleet_inspections_driver", "fleet_inspections", "driver_profiles", ["driver_id"], ["id"])
    for name in ("trailer_id", "custody_session_id", "driver_id"):
        op.create_index(f"ix_fleet_inspections_{name}", "fleet_inspections", [name])

    for column in (
        sa.Column("trailer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("custody_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("driver_id_at_occurrence", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("incident_type", sa.String(32), nullable=False, server_default="other"),
    ):
        op.add_column("fleet_incidents", column)
    op.create_foreign_key("fk_fleet_incidents_trailer", "fleet_incidents", "fleet_trailers", ["trailer_id"], ["id"])
    op.create_foreign_key(
        "fk_fleet_incidents_custody",
        "fleet_incidents",
        "equipment_custody_sessions",
        ["custody_session_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_fleet_incidents_driver",
        "fleet_incidents",
        "driver_profiles",
        ["driver_id_at_occurrence"],
        ["id"],
    )
    for name in ("trailer_id", "custody_session_id", "driver_id_at_occurrence"):
        op.create_index(f"ix_fleet_incidents_{name}", "fleet_incidents", [name])

    op.create_table(
        "fleet_incident_events",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("data_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        *_base_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["fleet_incidents.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
    )
    for name, columns in (
        ("ix_fleet_incident_events_tenant_id", ["tenant_id"]),
        ("ix_fleet_incident_events_incident_id", ["incident_id"]),
        ("ix_fleet_incident_events_actor_user_id", ["actor_user_id"]),
        ("ix_fleet_incident_events_event_type", ["event_type"]),
        ("ix_fleet_incident_events_occurred_at", ["occurred_at"]),
        ("ix_fleet_incident_events_timeline", ["tenant_id", "incident_id", "occurred_at"]),
    ):
        op.create_index(name, "fleet_incident_events", columns)

    op.create_table(
        "fleet_accountability_reviews",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("duty_considered", sa.String(64), nullable=True),
        sa.Column("finding", sa.String(48), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.CheckConstraint(
            "status IN ('pending', 'in_review', 'awaiting_driver_response', "
            "'disputed', 'finalized', 'reopened', 'voided')",
            name="ck_fleet_accountability_reviews_status",
        ),
        sa.CheckConstraint(
            "finding IS NULL OR finding IN ('not_attributable', 'insufficient_evidence', "
            "'driver_duty_issue', 'shared_responsibility', 'non_driver_issue')",
            name="ck_fleet_accountability_reviews_finding",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["fleet_incidents.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("incident_id", "revision", name="uq_fleet_accountability_review_revision"),
    )
    for name, columns in (
        ("ix_fleet_accountability_reviews_tenant_id", ["tenant_id"]),
        ("ix_fleet_accountability_reviews_incident_id", ["incident_id"]),
        ("ix_fleet_accountability_reviews_status", ["status"]),
    ):
        op.create_index(name, "fleet_accountability_reviews", columns)

    op.create_table(
        "fleet_accountability_attributions",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("party_type", sa.String(32), nullable=False),
        sa.Column("attribution", sa.String(24), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        *_base_columns(),
        sa.CheckConstraint(
            "party_type IN ('driver', 'maintenance', 'dispatch', 'equipment', "
            "'third_party', 'road_weather', 'unknown')",
            name="ck_fleet_accountability_attributions_party_type",
        ),
        sa.CheckConstraint(
            "attribution IN ('primary', 'contributing', 'not_attributable')",
            name="ck_fleet_accountability_attributions_value",
        ),
        sa.CheckConstraint(
            "(party_type = 'driver' AND driver_id IS NOT NULL) OR "
            "(party_type <> 'driver' AND driver_id IS NULL)",
            name="ck_fleet_accountability_attributions_driver",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["fleet_accountability_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["driver_id"], ["driver_profiles.id"]),
    )
    for name, columns in (
        ("ix_fleet_accountability_attributions_tenant_id", ["tenant_id"]),
        ("ix_fleet_accountability_attributions_review_id", ["review_id"]),
        ("ix_fleet_accountability_attributions_driver_id", ["driver_id"]),
    ):
        op.create_index(name, "fleet_accountability_attributions", columns)

    op.create_table(
        "fleet_driver_review_responses",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_type", sa.String(24), nullable=False),
        sa.Column("statement", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        *_base_columns(),
        sa.CheckConstraint(
            "response_type IN ('acknowledged', 'context', 'dispute')",
            name="ck_fleet_driver_review_responses_type",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["fleet_accountability_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["driver_id"], ["driver_profiles.id"]),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"]),
    )
    for name, columns in (
        ("ix_fleet_driver_review_responses_tenant_id", ["tenant_id"]),
        ("ix_fleet_driver_review_responses_review_id", ["review_id"]),
        ("ix_fleet_driver_review_responses_driver_id", ["driver_id"]),
    ):
        op.create_index(name, "fleet_driver_review_responses", columns)


def downgrade() -> None:
    op.drop_table("fleet_driver_review_responses")
    op.drop_table("fleet_accountability_attributions")
    op.drop_table("fleet_accountability_reviews")
    op.drop_table("fleet_incident_events")

    for name in ("driver_id_at_occurrence", "custody_session_id", "trailer_id"):
        op.drop_index(f"ix_fleet_incidents_{name}", table_name="fleet_incidents")
    op.drop_constraint("fk_fleet_incidents_driver", "fleet_incidents", type_="foreignkey")
    op.drop_constraint("fk_fleet_incidents_custody", "fleet_incidents", type_="foreignkey")
    op.drop_constraint("fk_fleet_incidents_trailer", "fleet_incidents", type_="foreignkey")
    for name in ("incident_type", "driver_id_at_occurrence", "custody_session_id", "trailer_id"):
        op.drop_column("fleet_incidents", name)

    for name in ("driver_id", "custody_session_id", "trailer_id"):
        op.drop_index(f"ix_fleet_inspections_{name}", table_name="fleet_inspections")
    op.drop_constraint("fk_fleet_inspections_driver", "fleet_inspections", type_="foreignkey")
    op.drop_constraint("fk_fleet_inspections_custody", "fleet_inspections", type_="foreignkey")
    op.drop_constraint("fk_fleet_inspections_trailer", "fleet_inspections", type_="foreignkey")
    for name in (
        "attested_name",
        "attestation_version",
        "attested_at",
        "inspection_type",
        "driver_id",
        "custody_session_id",
        "trailer_id",
    ):
        op.drop_column("fleet_inspections", name)

    op.drop_table("equipment_custody_assets")
    op.drop_table("equipment_custody_sessions")
    op.execute("DROP INDEX IF EXISTS ix_fleet_trailers_tenant_normalized_vin")
    op.drop_table("fleet_trailers")
    op.drop_table("driver_profiles")
    # PostgreSQL enum values are intentionally not removed on downgrade; doing
    # so requires recreating the shared type and can corrupt existing users.
