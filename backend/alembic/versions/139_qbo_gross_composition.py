"""Freeze versioned gross-invoice accounting without rewriting financial history."""
from alembic import op
import sqlalchemy as sa

revision = "139_qbo_gross_composition"
down_revision = "138_payment_fee_journal_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoice_settlements", sa.Column(
        "accounting_composition_version", sa.String(32), nullable=False,
        server_default="legacy_principal_v1"))
    op.add_column("invoice_settlements", sa.Column("accounting_projection_revision", sa.String(64), nullable=True))
    for name in ("accounting_fee_line_ids", "accounting_projection_snapshot"):
        op.add_column("invoice_settlements", sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.create_check_constraint("ck_invoice_settlement_composition", "invoice_settlements",
        "accounting_composition_version IN ('legacy_principal_v1','gross_invoice_v1')")
    for name in ("qbo_card_fee_item_id", "qbo_card_fee_tax_code_id"):
        op.add_column("tenant_payment_provider_configurations", sa.Column(name, sa.String(255), nullable=True))
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION guard_db048_gross_composition() RETURNS trigger AS $$
            BEGIN
              IF NEW.accounting_composition_version IS DISTINCT FROM OLD.accounting_composition_version THEN
                RAISE EXCEPTION 'DB-048 accounting composition is immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_db048_gross_composition
            BEFORE UPDATE OF accounting_composition_version ON invoice_settlements
            FOR EACH ROW EXECUTE FUNCTION guard_db048_gross_composition()
        """))
        op.execute(sa.text("""
            CREATE FUNCTION guard_db048_gross_mapping() RETURNS trigger AS $$
            BEGIN
              IF NEW.qbo_card_fee_item_id IS DISTINCT FROM OLD.qbo_card_fee_item_id
                OR NEW.qbo_card_fee_tax_code_id IS DISTINCT FROM OLD.qbo_card_fee_tax_code_id THEN
                RAISE EXCEPTION 'DB-048 gross accounting mapping is immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_db048_gross_mapping
            BEFORE UPDATE OF qbo_card_fee_item_id, qbo_card_fee_tax_code_id
            ON tenant_payment_provider_configurations
            FOR EACH ROW EXECUTE FUNCTION guard_db048_gross_mapping()
        """))


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("""
        SELECT 1 FROM invoice_settlements
        WHERE accounting_composition_version != 'legacy_principal_v1'
           OR accounting_projection_revision IS NOT NULL
           OR CAST(accounting_fee_line_ids AS TEXT) != '{}'
           OR CAST(accounting_projection_snapshot AS TEXT) != '{}'
        UNION ALL
        SELECT 1 FROM tenant_payment_provider_configurations
        WHERE qbo_card_fee_item_id IS NOT NULL OR qbo_card_fee_tax_code_id IS NOT NULL
        LIMIT 1
    """)).first():
        raise RuntimeError("Cannot remove persisted gross accounting composition or mappings")
    if connection.dialect.name == "postgresql":
        op.execute(sa.text("DROP TRIGGER trg_db048_gross_mapping ON tenant_payment_provider_configurations"))
        op.execute(sa.text("DROP FUNCTION guard_db048_gross_mapping()"))
        op.execute(sa.text("DROP TRIGGER trg_db048_gross_composition ON invoice_settlements"))
        op.execute(sa.text("DROP FUNCTION guard_db048_gross_composition()"))
    for name in ("qbo_card_fee_tax_code_id", "qbo_card_fee_item_id"):
        op.drop_column("tenant_payment_provider_configurations", name)
    op.drop_constraint("ck_invoice_settlement_composition", "invoice_settlements", type_="check")
    for name in ("accounting_projection_snapshot", "accounting_fee_line_ids", "accounting_projection_revision", "accounting_composition_version"):
        op.drop_column("invoice_settlements", name)
