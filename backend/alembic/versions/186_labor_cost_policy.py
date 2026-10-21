"""Append-only owner technician cost policy and job-cost review evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "186_labor_cost_policy"
down_revision = "185_callrail_inquiry_main_merge"
branch_labels = None
depends_on = None


def upgrade():
    uuid, json = postgresql.UUID(as_uuid=True), postgresql.JSONB()
    for table, subject, parent_table in (
        ("technician_cost_policy_revisions", "mechanic_id", "users"),
        ("job_cost_reviews", "order_id", "repair_orders"),
    ):
        columns = [sa.Column("id", uuid, primary_key=True),
            sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column(subject, uuid, sa.ForeignKey(f"{parent_table}.id"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("supersedes_id", uuid, sa.ForeignKey(f"{table}.id"), nullable=True, unique=True),
            sa.Column("request_sha256", sa.String(64), nullable=False),
            sa.Column("idempotency_key", uuid, nullable=False),
            sa.Column("approved_by_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("version > 0", name=f"ck_{table}_version"),
            sa.CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name=f"ck_{table}_digest"),
            sa.UniqueConstraint("tenant_id", subject, "version", name=f"uq_{table}_version"),
            sa.UniqueConstraint("tenant_id", "idempotency_key", name=f"uq_{table}_key")]
        if subject == "mechanic_id":
            columns.append(sa.Column("policy", json, nullable=False))
        else:
            columns.extend([
                sa.Column("business_classification", sa.String(16), nullable=False),
                sa.Column("reason", sa.String(500), nullable=False),
                sa.Column("source_fingerprint", sa.String(64), nullable=False),
                sa.Column("policy_heads_digest", sa.String(64), nullable=False),
                sa.Column("calculation_version", sa.String(32), nullable=False),
                sa.Column("time_capture", sa.String(32), nullable=False),
                sa.Column("reviewed_exception_ids", json, nullable=False),
                sa.Column("snapshot", json, nullable=False),
                sa.CheckConstraint("business_classification IN ('real','test','unknown')", name="ck_job_cost_classification"),
                sa.CheckConstraint("time_capture IN ('complete','incomplete','no_internal_labor')", name="ck_job_cost_time_capture"),
                sa.CheckConstraint("source_fingerprint ~ '^[0-9a-f]{64}$' AND policy_heads_digest ~ '^[0-9a-f]{64}$'", name="ck_job_cost_source_digests")])
        op.create_table(table, *columns)
        op.create_index(f"ix_{table}_tenant", table, ["tenant_id", subject, "version"])
    op.execute("""
CREATE FUNCTION db136_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'A1 evidence is append-only'; END $$;
""")
    op.execute("""
CREATE FUNCTION db136_metadata_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior_id UUID; prior_version INTEGER; prior_policy JSONB; shop_tz TEXT;
        item JSONB; previous_end TIMESTAMPTZ; start_at TIMESTAMPTZ; end_at TIMESTAMPTZ;
        activation TIMESTAMPTZ; position INTEGER := 0; exception_id TEXT;
BEGIN
  SELECT timezone INTO shop_tz FROM tenants WHERE id=NEW.tenant_id AND is_active AND deleted_at IS NULL FOR UPDATE;
  IF shop_tz IS NULL OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.approved_by_user_id
       AND tenant_id=NEW.tenant_id AND role='garage_owner' AND is_active AND deleted_at IS NULL) THEN
    RAISE EXCEPTION 'Invalid A1 owner scope';
  END IF;
  IF TG_TABLE_NAME='technician_cost_policy_revisions' THEN
    IF NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.mechanic_id AND tenant_id=NEW.tenant_id
                  AND role='mechanic' AND is_active AND deleted_at IS NULL) THEN
      RAISE EXCEPTION 'Invalid A1 technician scope'; END IF;
    SELECT id,version,policy INTO prior_id,prior_version,prior_policy FROM technician_cost_policy_revisions
      WHERE tenant_id=NEW.tenant_id AND mechanic_id=NEW.mechanic_id ORDER BY version DESC LIMIT 1;
    IF NEW.version <> COALESCE(prior_version,0)+1 OR NEW.supersedes_id IS DISTINCT FROM prior_id THEN
      RAISE EXCEPTION 'Invalid A1 policy successor'; END IF;
    IF NEW.version > 1000 OR octet_length(NEW.policy::text)>65536 OR jsonb_typeof(NEW.policy)<>'object'
       OR (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(NEW.policy) key) <>
          ARRAY['activation_at','activation_local_date','basis','currency','policy_version','reason','segments','shop_timezone']::text[]
       OR NEW.policy->>'policy_version'<>'1' OR jsonb_typeof(NEW.policy->'policy_version')<>'number'
       OR NEW.policy->>'currency'<>'USD' OR NEW.policy->>'basis'<>'owner_declared_loaded_direct'
       OR jsonb_typeof(NEW.policy->'currency') IS DISTINCT FROM 'string'
       OR jsonb_typeof(NEW.policy->'basis') IS DISTINCT FROM 'string'
       OR jsonb_typeof(NEW.policy->'shop_timezone') IS DISTINCT FROM 'string'
       OR jsonb_typeof(NEW.policy->'activation_local_date') IS DISTINCT FROM 'string'
       OR jsonb_typeof(NEW.policy->'activation_at') IS DISTINCT FROM 'string'
       OR jsonb_typeof(NEW.policy->'reason') IS DISTINCT FROM 'string'
       OR NEW.policy->>'shop_timezone'<>shop_tz OR NEW.policy->>'activation_local_date'<>'2026-10-20'
       OR jsonb_typeof(NEW.policy->'segments')<>'array' OR jsonb_array_length(NEW.policy->'segments')>100
       OR char_length(btrim(NEW.policy->>'reason')) NOT BETWEEN 1 AND 500 THEN
      RAISE EXCEPTION 'Invalid A1 policy'; END IF;
    activation := (NEW.policy->>'activation_at')::timestamptz;
    IF activation IS DISTINCT FROM (CASE WHEN prior_id IS NULL THEN timestamp '2026-10-20 00:00:00' AT TIME ZONE shop_tz
                      ELSE (prior_policy->>'activation_at')::timestamptz END) THEN
      RAISE EXCEPTION 'Invalid A1 activation'; END IF;
    FOR item IN SELECT * FROM jsonb_array_elements(NEW.policy->'segments') LOOP
      IF jsonb_typeof(item)<>'object' OR (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(item) key) <>
          ARRAY['effective_from','effective_to','hourly_cost','inclusions']::text[]
         OR jsonb_typeof(item->'hourly_cost')<>'string' OR (item->>'hourly_cost') !~ '^(0|[1-9][0-9]{0,4})(\\.[0-9]{1,4})?$'
         OR jsonb_typeof(item->'inclusions') IS DISTINCT FROM 'string'
         OR jsonb_typeof(item->'effective_from') IS DISTINCT FROM 'string'
         OR (item->>'effective_to' IS NOT NULL AND jsonb_typeof(item->'effective_to') IS DISTINCT FROM 'string')
         OR (item->>'hourly_cost')::numeric NOT BETWEEN 0.0001 AND 10000
         OR char_length(btrim(item->>'inclusions')) NOT BETWEEN 1 AND 500
         OR (item->>'effective_from') !~ 'Z$|\\+00:00$'
         OR (item->>'effective_to' IS NOT NULL AND (item->>'effective_to') !~ 'Z$|\\+00:00$') THEN
        RAISE EXCEPTION 'Invalid A1 segment'; END IF;
      start_at := (item->>'effective_from')::timestamptz; end_at := (item->>'effective_to')::timestamptz;
      IF start_at<activation OR (end_at IS NOT NULL AND end_at<=start_at)
         OR (position>0 AND (previous_end IS NULL OR start_at<previous_end)) THEN
        RAISE EXCEPTION 'Invalid A1 interval'; END IF;
      position := position+1; previous_end:=end_at;
    END LOOP;
  ELSE
    IF NOT EXISTS(SELECT 1 FROM repair_orders WHERE id=NEW.order_id AND tenant_id=NEW.tenant_id AND deleted_at IS NULL) THEN
      RAISE EXCEPTION 'Invalid A1 job scope'; END IF;
    SELECT id,version INTO prior_id,prior_version FROM job_cost_reviews WHERE tenant_id=NEW.tenant_id
      AND order_id=NEW.order_id ORDER BY version DESC LIMIT 1;
    IF NEW.version<>COALESCE(prior_version,0)+1 OR NEW.supersedes_id IS DISTINCT FROM prior_id
       OR NEW.calculation_version<>'db136-v1' OR char_length(btrim(NEW.reason)) NOT BETWEEN 1 AND 500
       OR jsonb_typeof(NEW.snapshot)<>'object' OR jsonb_typeof(NEW.reviewed_exception_ids)<>'array'
       OR jsonb_array_length(NEW.reviewed_exception_ids)>500
       OR (SELECT count(*) FROM jsonb_array_elements_text(NEW.reviewed_exception_ids)) <>
          (SELECT count(DISTINCT value) FROM jsonb_array_elements_text(NEW.reviewed_exception_ids) value) THEN
      RAISE EXCEPTION 'Invalid A1 review'; END IF;
    FOR exception_id IN SELECT * FROM jsonb_array_elements_text(NEW.reviewed_exception_ids) LOOP
      IF NOT EXISTS(SELECT 1 FROM mechanic_time_sessions WHERE id=exception_id::uuid
                    AND tenant_id=NEW.tenant_id AND repair_order_id=NEW.order_id) THEN
        RAISE EXCEPTION 'Invalid A1 exception scope'; END IF;
    END LOOP;
  END IF;
  RETURN NEW;
END $$;
""")
    for table in ("technician_cost_policy_revisions", "job_cost_reviews"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION db136_immutable()")
        op.execute(f"CREATE TRIGGER {table}_insert_guard BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION db136_metadata_insert()")


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM technician_cost_policy_revisions) OR EXISTS(SELECT 1 FROM job_cost_reviews)
      THEN RAISE EXCEPTION 'Cannot remove approved A1 evidence'; END IF; END $$""")
    for table in ("job_cost_reviews", "technician_cost_policy_revisions"):
        op.drop_table(table)
    op.execute("DROP FUNCTION db136_metadata_insert();")
    op.execute("DROP FUNCTION db136_immutable();")
