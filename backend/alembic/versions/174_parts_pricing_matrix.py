"""DB132 immutable parts price rules and attachment provenance; no price backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "174_parts_pricing_matrix"
down_revision = "173_repair_order_schedule"
branch_labels = None
depends_on = None
UUID = postgresql.UUID(as_uuid=True)


def base():
    return [sa.Column("id", UUID, primary_key=True),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade():
    op.create_table("parts_price_matrices", *base(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("current_revision", sa.Integer, nullable=False),
        sa.Column("version", sa.BigInteger, nullable=False, server_default="1"),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("archived_by", UUID, sa.ForeignKey("users.id")),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_parts_price_matrices_tenant_id"),
        sa.CheckConstraint("version >= 1 AND current_revision >= 1", name="ck_parts_matrix_version"))
    op.create_index("uq_parts_matrix_active_name", "parts_price_matrices", ["tenant_id", sa.text("lower(name)")], unique=True, postgresql_where=sa.text("archived_at IS NULL"))
    op.create_table("parts_price_matrix_revisions", *base(),
        sa.Column("matrix_id", UUID, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("name_snapshot", sa.String(120), nullable=False),
        sa.Column("bands", sa.JSON, nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_parts_price_revisions_tenant_id"),
        sa.UniqueConstraint("tenant_id", "matrix_id", "revision", name="uq_parts_price_revision_number"),
        sa.ForeignKeyConstraint(["tenant_id", "matrix_id"], ["parts_price_matrices.tenant_id", "parts_price_matrices.id"], name="fk_parts_price_revision_matrix"))
    op.create_table("parts_pricing_policies",
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("default_matrix_id", UUID),
        sa.Column("generation", sa.BigInteger, server_default="0", nullable=False),
        sa.Column("updated_by", UUID, sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("generation >= 0", name="ck_parts_pricing_generation"),
        sa.ForeignKeyConstraint(["tenant_id", "default_matrix_id"], ["parts_price_matrices.tenant_id", "parts_price_matrices.id"], name="fk_parts_pricing_policy_matrix"))
    for field in ("pricing_cost_floor", "minimum_sale_price"):
        op.add_column("inventory", sa.Column(field, sa.Numeric(10, 2), nullable=True))
        op.create_check_constraint("ck_inventory_" + field, "inventory", f"{field} IS NULL OR {field} >= 0")
    op.add_column("inventory", sa.Column("fixed_sales_price", sa.Boolean, server_default=sa.false(), nullable=False))
    op.add_column("inventory", sa.Column("pricing_version", sa.BigInteger, server_default="0", nullable=False))
    for table in ("parts_usage", "counter_sale_lines"):
        op.add_column(table, sa.Column("pricing_snapshot", sa.JSON, nullable=True))
        op.add_column(table, sa.Column("pricing_matrix_revision_id", UUID, nullable=True))
        op.create_foreign_key("fk_" + table + "_pricing_revision", table, "parts_price_matrix_revisions", ["tenant_id", "pricing_matrix_revision_id"], ["tenant_id", "id"])
    op.add_column("parts_usage", sa.Column("pricing_version", sa.BigInteger, server_default="0", nullable=False))
    op.add_column("parts_usage", sa.Column("source_component_id", UUID, nullable=True))
    op.create_table("parts_pricing_events", *base(),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("old_version", sa.BigInteger), sa.Column("new_version", sa.BigInteger),
        sa.Column("reason", sa.String(500)),
        sa.Column("identity_snapshot", sa.JSON, nullable=False),
        sa.Column("before_values", sa.JSON, nullable=False), sa.Column("after_values", sa.JSON, nullable=False),
        *[sa.Column(name, UUID) for name in ("matrix_id", "revision_id", "inventory_id", "counter_sale_id", "counter_line_id")],
        *[sa.ForeignKeyConstraint(["tenant_id", column], [table + ".tenant_id", table + ".id"], name="fk_pricing_event_" + column)
          for column, table in (("matrix_id", "parts_price_matrices"), ("revision_id", "parts_price_matrix_revisions"), ("inventory_id", "inventory"), ("counter_sale_id", "counter_sales"), ("counter_line_id", "counter_sale_lines"))])
    op.create_index("ix_parts_pricing_event_entity", "parts_pricing_events", ["tenant_id", "entity_type", "entity_id", "created_at", "id"])
    op.create_index("ix_parts_pricing_event_tenant", "parts_pricing_events", ["tenant_id", "created_at", "id"])
    op.execute("""CREATE FUNCTION db132_reject_evidence_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'DB132 pricing evidence is append-only'; END; $$""")
    for table in ("parts_price_matrix_revisions", "parts_pricing_events"):
        op.execute(f"CREATE TRIGGER trg_db132_{table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION db132_reject_evidence_mutation()")
    # Immutable origin columns are separate from the mutable charged-price overlay.
    op.execute("""CREATE FUNCTION db132_reject_snapshot_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF OLD.pricing_snapshot IS NOT NULL AND
           (OLD.pricing_snapshot::jsonb IS DISTINCT FROM NEW.pricing_snapshot::jsonb OR
            OLD.pricing_matrix_revision_id IS DISTINCT FROM NEW.pricing_matrix_revision_id)
        THEN RAISE EXCEPTION 'DB132 attachment pricing origin is immutable'; END IF;
        RETURN NEW;
      END; $$""")
    for table in ("parts_usage", "counter_sale_lines"):
        op.execute(f"CREATE TRIGGER trg_db132_{table}_snapshot BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION db132_reject_snapshot_mutation()")


def downgrade():
    # Disposable database verification only. Production rollbacks retain evidence.
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM parts_pricing_events) OR EXISTS
      (SELECT 1 FROM parts_price_matrix_revisions) THEN RAISE EXCEPTION
      'DB132 downgrade refused: pricing evidence exists'; END IF; END $$""")
    for table in ("parts_usage", "counter_sale_lines"):
        op.execute(f"DROP TRIGGER trg_db132_{table}_snapshot ON {table}")
    op.execute("DROP FUNCTION db132_reject_snapshot_mutation()")
    op.drop_table("parts_pricing_events")
    for table in ("parts_usage", "counter_sale_lines"):
        op.drop_constraint("fk_" + table + "_pricing_revision", table, type_="foreignkey")
        op.drop_column(table, "pricing_matrix_revision_id")
        op.drop_column(table, "pricing_snapshot")
    op.drop_column("parts_usage", "source_component_id")
    op.drop_column("parts_usage", "pricing_version")
    for field in ("pricing_cost_floor", "minimum_sale_price"):
        op.drop_constraint("ck_inventory_" + field, "inventory", type_="check")
        op.drop_column("inventory", field)
    op.drop_column("inventory", "fixed_sales_price")
    op.drop_column("inventory", "pricing_version")
    op.drop_table("parts_pricing_policies")
    op.drop_table("parts_price_matrix_revisions")
    op.drop_table("parts_price_matrices")
    op.execute("DROP FUNCTION db132_reject_evidence_mutation()")
