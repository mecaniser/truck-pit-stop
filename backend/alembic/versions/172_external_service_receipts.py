"""Private retained outside-shop receipt metadata, bytes and action evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "172_external_service_receipts"
down_revision = "171_ets_source_evidence"
branch_labels = None
depends_on = None


def _base():
    return [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)]


def _uuid(name):
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=False)


def upgrade():
    op.create_table("external_service_receipts", *_base(), _uuid("tenant_id"), _uuid("record_id"), _uuid("uploaded_vehicle_id"),
        sa.Column("filename", sa.String(180), nullable=False),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("created_by_user_id"), sa.Column("created_by_name", sa.String(255), nullable=False),
        _uuid("updated_by_user_id"), sa.Column("updated_by_name", sa.String(255), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_external_receipt_tenant_id"),
        sa.UniqueConstraint("tenant_id", "record_id", "id", name="uq_external_receipt_record_id"),
        sa.UniqueConstraint("tenant_id", "record_id", "content_sha256", name="uq_external_receipt_content"),
        sa.ForeignKeyConstraint(["tenant_id", "record_id"], ["external_service_records.tenant_id", "external_service_records.id"], name="fk_external_receipt_record", ondelete="RESTRICT"),
        sa.CheckConstraint("version >= 1", name="ck_external_receipt_version"),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 5242880", name="ck_external_receipt_size"),
        sa.CheckConstraint("media_type IN ('application/pdf','image/jpeg','image/png')", name="ck_external_receipt_type"))
    op.create_index("ix_external_service_receipts_id", "external_service_receipts", ["id"])
    op.create_index("ix_external_receipt_record_created", "external_service_receipts", ["tenant_id", "record_id", "created_at", "id"])
    op.create_table("external_service_receipt_blobs", *_base(), _uuid("tenant_id"), _uuid("receipt_id"),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.UniqueConstraint("tenant_id", "receipt_id", name="uq_external_receipt_blob"),
        sa.ForeignKeyConstraint(["tenant_id", "receipt_id"], ["external_service_receipts.tenant_id", "external_service_receipts.id"], name="fk_external_receipt_blob", ondelete="RESTRICT"),
        sa.CheckConstraint("octet_length(content) BETWEEN 1 AND 5242880", name="ck_external_receipt_blob_size"))
    op.create_index("ix_external_service_receipt_blobs_id", "external_service_receipt_blobs", ["id"])
    op.create_table("external_service_receipt_events", *_base(), _uuid("tenant_id"), _uuid("record_id"), _uuid("receipt_id"),
        _uuid("request_id"), sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("action", sa.String(16), nullable=False),
        _uuid("actor_user_id"), sa.Column("actor_name", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True), sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "record_id", "receipt_id"], ["external_service_receipts.tenant_id", "external_service_receipts.record_id", "external_service_receipts.id"], name="fk_external_receipt_event", ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "request_id", name="uq_external_receipt_request"),
        sa.UniqueConstraint("tenant_id", "receipt_id", "version", name="uq_external_receipt_revision"),
        sa.CheckConstraint("version >= 1", name="ck_external_receipt_event_version"),
        sa.CheckConstraint("action IN ('upload','remove','restore')", name="ck_external_receipt_action"))
    op.create_index("ix_external_service_receipt_events_id", "external_service_receipt_events", ["id"])


def downgrade():
    # Disposable empty databases only. Production rollback keeps retained files.
    op.drop_table("external_service_receipt_events")
    op.drop_table("external_service_receipt_blobs")
    op.drop_table("external_service_receipts")
