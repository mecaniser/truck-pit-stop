"""DB133 customer defaults and immutable new-work policy; no money backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '175_customer_pricing_defaults'
down_revision = '174_parts_pricing_matrix'
branch_labels = None
depends_on = None
UUID = postgresql.UUID(as_uuid=True)


def upgrade():
    for column in [sa.Column('pricing_labor_rate', sa.Numeric(10, 2)),
                   sa.Column('parts_price_matrix_id', UUID),
                   sa.Column('pricing_version', sa.BigInteger, nullable=False, server_default='0'),
                   sa.Column('pricing_updated_at', sa.DateTime(timezone=True)),
                   sa.Column('pricing_updated_by', UUID)]:
        op.add_column('customers', column)
    op.create_check_constraint('ck_customer_pricing_rate', 'customers', 'pricing_labor_rate IS NULL OR (pricing_labor_rate > 0 AND pricing_labor_rate <= 99999999.99)')
    op.create_check_constraint('ck_customer_pricing_version', 'customers', 'pricing_version >= 0')
    op.create_foreign_key('fk_customer_pricing_matrix', 'customers', 'parts_price_matrices', ['tenant_id', 'parts_price_matrix_id'], ['tenant_id', 'id'])
    for table in ('repair_orders', 'counter_sales'):
        op.add_column(table, sa.Column('pricing_policy_snapshot', sa.JSON))
        op.add_column(table, sa.Column('pricing_matrix_revision_id', UUID))
        op.create_foreign_key('fk_' + table + '_account_revision', table, 'parts_price_matrix_revisions', ['tenant_id', 'pricing_matrix_revision_id'], ['tenant_id', 'id'])
        op.create_check_constraint('ck_' + table + '_account_policy', table,
            "((pricing_policy_snapshot IS NULL AND pricing_matrix_revision_id IS NULL) OR "
            "(pricing_policy_snapshot IS NOT NULL AND pricing_policy_snapshot->>'schema_version' = '1' AND "
            "((pricing_policy_snapshot->'parts'->>'mode' = 'catalog' AND pricing_matrix_revision_id IS NULL AND pricing_policy_snapshot->'parts'->>'matrix' IS NULL) OR "
            "(pricing_policy_snapshot->'parts'->>'mode' = 'matrix' AND pricing_matrix_revision_id IS NOT NULL AND pricing_policy_snapshot->'parts'->'matrix'->>'revision_id' = pricing_matrix_revision_id::text)))) IS TRUE")
        op.create_index('ix_' + table + '_account_policy_customer', table, ['tenant_id', sa.text("(pricing_policy_snapshot->>'customer_id')")], postgresql_where=sa.text('pricing_policy_snapshot IS NOT NULL'))
    op.add_column('labor', sa.Column('pricing_snapshot', sa.JSON))
    op.add_column('labor', sa.Column('pricing_source', sa.String(16)))
    op.create_check_constraint('ck_labor_pricing_source', 'labor', "pricing_source IS NULL OR pricing_source IN ('default','manual')")
    op.create_table('account_pricing_events',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('tenant_id', UUID, sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('entity_type', sa.String(32), nullable=False), sa.Column('entity_id', UUID, nullable=False),
        sa.Column('customer_id', UUID), sa.Column('customer_name', sa.String(255)),
        sa.Column('repair_order_id', UUID), sa.Column('counter_sale_id', UUID),
        sa.Column('actor_id', UUID, nullable=False), sa.Column('actor_name', sa.String(255)), sa.Column('actor_role', sa.String(32), nullable=False),
        sa.Column('correlation_id', UUID, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('old_version', sa.BigInteger), sa.Column('new_version', sa.BigInteger),
        sa.Column('reason', sa.String(500)), sa.Column('before_values', sa.JSON, nullable=False), sa.Column('after_values', sa.JSON, nullable=False),
        sa.Column('matrix_id', UUID), sa.Column('revision_id', UUID),
        sa.CheckConstraint("entity_type IN ('customer_policy','labor','counter_policy')", name='ck_account_pricing_entity'),
        sa.ForeignKeyConstraint(['tenant_id', 'matrix_id'], ['parts_price_matrices.tenant_id', 'parts_price_matrices.id'], name='fk_account_event_matrix'),
        sa.ForeignKeyConstraint(['tenant_id', 'revision_id'], ['parts_price_matrix_revisions.tenant_id', 'parts_price_matrix_revisions.id'], name='fk_account_event_revision'))
    op.create_index('ix_account_pricing_event_entity', 'account_pricing_events', ['tenant_id', 'entity_type', 'entity_id', 'new_version', 'id'])
    op.create_index('ix_account_pricing_event_customer', 'account_pricing_events', ['tenant_id', 'customer_id'])
    op.execute("CREATE TRIGGER trg_db133_account_events BEFORE UPDATE OR DELETE ON account_pricing_events FOR EACH ROW EXECUTE FUNCTION db132_reject_evidence_mutation()")
    op.execute("""CREATE FUNCTION db133_reject_policy_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF OLD.pricing_policy_snapshot IS NOT NULL AND
          (OLD.pricing_policy_snapshot::jsonb IS DISTINCT FROM NEW.pricing_policy_snapshot::jsonb OR
           OLD.pricing_matrix_revision_id IS DISTINCT FROM NEW.pricing_matrix_revision_id)
        THEN RAISE EXCEPTION 'DB133 order pricing policy is immutable'; END IF;
        RETURN NEW;
      END; $$""")
    op.execute('CREATE TRIGGER trg_db133_order_policy BEFORE UPDATE ON repair_orders FOR EACH ROW EXECUTE FUNCTION db133_reject_policy_mutation()')
    op.execute("""CREATE FUNCTION db133_reject_labor_origin_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF OLD.pricing_snapshot IS NOT NULL AND OLD.pricing_snapshot::jsonb IS DISTINCT FROM NEW.pricing_snapshot::jsonb
        THEN RAISE EXCEPTION 'DB133 labor pricing origin is immutable'; END IF;
        RETURN NEW;
      END; $$""")
    op.execute('CREATE TRIGGER trg_db133_labor_origin BEFORE UPDATE ON labor FOR EACH ROW EXECUTE FUNCTION db133_reject_labor_origin_mutation()')
    op.execute("""CREATE FUNCTION db133_counter_policy_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (OLD.pricing_policy_snapshot::jsonb IS DISTINCT FROM NEW.pricing_policy_snapshot::jsonb OR
            OLD.pricing_matrix_revision_id IS DISTINCT FROM NEW.pricing_matrix_revision_id)
           AND (OLD.status <> 'draft' OR NEW.status <> 'draft' OR NEW.pricing_policy_snapshot IS NULL OR OLD.customer_id IS NOT DISTINCT FROM NEW.customer_id)
        THEN RAISE EXCEPTION 'DB133 counter policy may change only with draft buyer'; END IF;
        RETURN NEW;
      END; $$""")
    op.execute('CREATE TRIGGER trg_db133_counter_policy BEFORE UPDATE ON counter_sales FOR EACH ROW EXECUTE FUNCTION db133_counter_policy_guard()')


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM account_pricing_events) OR EXISTS
      (SELECT 1 FROM customers WHERE pricing_version <> 0 OR pricing_labor_rate IS NOT NULL OR parts_price_matrix_id IS NOT NULL) OR EXISTS
      (SELECT 1 FROM repair_orders WHERE pricing_policy_snapshot IS NOT NULL) OR EXISTS
      (SELECT 1 FROM counter_sales WHERE pricing_policy_snapshot IS NOT NULL) OR EXISTS
      (SELECT 1 FROM labor WHERE pricing_snapshot IS NOT NULL OR pricing_source IS NOT NULL)
      THEN RAISE EXCEPTION 'DB133 downgrade refused: account pricing evidence exists'; END IF; END $$""")
    for table, trigger in (('repair_orders','order_policy'), ('labor','labor_origin'), ('counter_sales','counter_policy')):
        op.execute(f'DROP TRIGGER trg_db133_{trigger} ON {table}')
    for fn in ('db133_reject_policy_mutation', 'db133_reject_labor_origin_mutation', 'db133_counter_policy_guard'):
        op.execute(f'DROP FUNCTION {fn}()')
    op.drop_table('account_pricing_events')
    op.drop_constraint('ck_labor_pricing_source', 'labor', type_='check')
    op.drop_column('labor', 'pricing_source'); op.drop_column('labor', 'pricing_snapshot')
    for table in ('repair_orders', 'counter_sales'):
        op.drop_index('ix_' + table + '_account_policy_customer', table_name=table)
        op.drop_constraint('ck_' + table + '_account_policy', table, type_='check')
        op.drop_constraint('fk_' + table + '_account_revision', table, type_='foreignkey')
        op.drop_column(table, 'pricing_matrix_revision_id'); op.drop_column(table, 'pricing_policy_snapshot')
    op.drop_constraint('fk_customer_pricing_matrix', 'customers', type_='foreignkey')
    op.drop_constraint('ck_customer_pricing_rate', 'customers', type_='check')
    op.drop_constraint('ck_customer_pricing_version', 'customers', type_='check')
    for name in ('pricing_labor_rate', 'parts_price_matrix_id', 'pricing_version', 'pricing_updated_at', 'pricing_updated_by'):
        op.drop_column('customers', name)
