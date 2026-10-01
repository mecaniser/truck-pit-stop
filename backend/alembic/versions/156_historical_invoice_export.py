"""DB-094: reviewed historical invoice export grants and scoped removals."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "156_historical_invoice_export"
down_revision = "155_fleet_invoice_api_keys"
branch_labels = None
depends_on = None


def _base():
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
    ]


def upgrade():
    op.create_table("historical_invoice_evidence", *_base(),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("repair_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repair_orders.id"), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_reference", sa.String(500), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_document", sa.LargeBinary(), nullable=False),
        sa.Column("source_content_type", sa.String(80), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_bill_to_name", sa.String(255), nullable=False),
        sa.Column("original_customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("merge_lineage_reference", sa.String(500), nullable=True),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("verified_target_customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_target_legal_name", sa.String(255), nullable=True),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.UniqueConstraint("tenant_id", "id", name="uq_historical_evidence_tenant_id"),
    )
    op.create_index("ix_historical_invoice_evidence_tenant_id", "historical_invoice_evidence", ["tenant_id"])
    op.create_index("ix_historical_invoice_evidence_invoice_id", "historical_invoice_evidence", ["invoice_id"])
    op.create_table("historical_invoice_mappings", *_base(),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=False, unique=True),
        sa.Column("target_customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("historical_invoice_evidence.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "invoice_id", name="uq_historical_mapping_invoice"),
    )
    op.create_index("ix_historical_invoice_mappings_tenant_id", "historical_invoice_mappings", ["tenant_id"])
    op.create_index("ix_historical_invoice_mappings_target_customer_id", "historical_invoice_mappings", ["target_customer_id"])
    op.create_table("historical_invoice_decisions", *_base(),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("historical_invoice_evidence.id"), nullable=True),
        sa.Column("evidence_sha256", sa.String(64), nullable=True),
        sa.Column("original_bill_to_name", sa.String(255), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("old_customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("new_customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("tenant_id", "invoice_id", "idempotency_key", name="uq_historical_decision_idempotency"),
    )
    op.create_index("ix_historical_invoice_decisions_tenant_id", "historical_invoice_decisions", ["tenant_id"])
    op.create_index("ix_historical_invoice_decisions_invoice_id", "historical_invoice_decisions", ["invoice_id"])
    op.create_table("fleet_invoice_scope_events", *_base(),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("historical_invoice_decisions.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("tenant_id", "invoice_id", "customer_id", "effective_at"):
        op.create_index(f"ix_fleet_invoice_scope_events_{column}", "fleet_invoice_scope_events", [column])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
        CREATE FUNCTION guard_historical_invoice_customer_identity() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF EXISTS (
              SELECT 1 FROM historical_invoice_mappings m
              WHERE m.tenant_id = OLD.tenant_id AND m.target_customer_id = OLD.id
            ) THEN
              RAISE EXCEPTION 'revoke reviewed historical invoice mappings before deleting bill-to';
            END IF;
            RETURN OLD;
          END IF;
          IF (OLD.first_name IS DISTINCT FROM NEW.first_name
              OR OLD.last_name IS DISTINCT FROM NEW.last_name
              OR OLD.company_name IS DISTINCT FROM NEW.company_name) AND EXISTS (
               SELECT 1 FROM historical_invoice_mappings m
               WHERE m.tenant_id = OLD.tenant_id AND m.target_customer_id = OLD.id
             ) THEN
            RAISE EXCEPTION 'revoke reviewed historical invoice mappings before changing bill-to identity';
          END IF;
          RETURN NEW;
        END $$
        """)
        op.execute("""
        CREATE TRIGGER tr_guard_historical_invoice_customer_identity
        BEFORE UPDATE OF first_name, last_name, company_name OR DELETE ON customers
        FOR EACH ROW EXECUTE FUNCTION guard_historical_invoice_customer_identity()
        """)


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER tr_guard_historical_invoice_customer_identity ON customers")
        op.execute("DROP FUNCTION guard_historical_invoice_customer_identity()")
    op.drop_table("fleet_invoice_scope_events")
    op.drop_table("historical_invoice_decisions")
    op.drop_table("historical_invoice_mappings")
    op.drop_table("historical_invoice_evidence")
