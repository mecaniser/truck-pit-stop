"""DB134 recurring maintenance programs; retain legacy scalars and all finances."""
from datetime import datetime, timezone
import json
from uuid import UUID, uuid5
from alembic import op
import sqlalchemy as sa

revision = '177_maintenance_programs'
down_revision = '176_merge_contact_pricing'
branch_labels = None
depends_on = None
NAMESPACE = UUID('6e2386ac-9ba3-49f2-875f-3c410bfb8783')


def upgrade():
    op.create_index("uq_repair_orders_tenant_identity", "repair_orders", ["tenant_id", "id"], unique=True)
    op.execute("""
CREATE TABLE maintenance_programs (
	vehicle_id UUID NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	version BIGINT NOT NULL, 
	mode VARCHAR(16) NOT NULL, 
	interval_days INTEGER, 
	interval_miles INTEGER, 
	interval_hours NUMERIC(12, 2), 
	target_due_on DATE, 
	target_miles INTEGER, 
	target_hours NUMERIC(12, 2), 
	target_provenance JSON NOT NULL, 
	service_id UUID, 
	service_snapshot JSON, 
	legacy_package JSON, 
	legacy_snapshot JSON, 
	current_cycle BIGINT NOT NULL, 
	baseline_generation BIGINT NOT NULL, 
	baseline_snapshot JSON, 
	controlling_completion_id UUID, 
	review_codes JSON NOT NULL, 
	archived_at TIMESTAMP WITH TIME ZONE, 
	created_by UUID, 
	updated_by UUID, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_maintenance_program_tenant UNIQUE (tenant_id, id), 
	CONSTRAINT fk_maintenance_program_vehicle FOREIGN KEY(tenant_id, vehicle_id) REFERENCES vehicles (tenant_id, id), 
	CONSTRAINT ck_maintenance_program_mode CHECK (mode IN ('independent','legacy')), 
	CONSTRAINT ck_maintenance_program_versions CHECK (version >= 1 AND current_cycle >= 1 AND baseline_generation >= 1), 
	CONSTRAINT ck_maintenance_program_days CHECK (interval_days IS NULL OR interval_days BETWEEN 1 AND 36500), 
	CONSTRAINT ck_maintenance_program_miles CHECK (interval_miles IS NULL OR interval_miles BETWEEN 1 AND 99999999), 
	CONSTRAINT ck_maintenance_program_hours CHECK (interval_hours IS NULL OR (interval_hours >= 0.01 AND interval_hours <= 10000000)), 
	CONSTRAINT ck_maintenance_program_enabled CHECK (mode='legacy' OR interval_days IS NOT NULL OR interval_miles IS NOT NULL OR interval_hours IS NOT NULL), 
	CONSTRAINT ck_maintenance_program_target_miles CHECK (target_miles IS NULL OR target_miles BETWEEN 0 AND 99999999), 
	CONSTRAINT ck_maintenance_program_target_hours CHECK (target_hours IS NULL OR (target_hours >= 0 AND target_hours <= 10000000)), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)
    """)
    op.execute('CREATE INDEX ix_maintenance_program_vehicle ON maintenance_programs (tenant_id, vehicle_id, archived_at)')
    op.execute("CREATE UNIQUE INDEX uq_maintenance_program_legacy ON maintenance_programs (tenant_id, vehicle_id) WHERE mode='legacy'")
    op.execute("""
CREATE TABLE maintenance_work_links (
	program_id UUID NOT NULL, 
	cycle BIGINT NOT NULL, 
	repair_order_id UUID NOT NULL, 
	program_version BIGINT NOT NULL, 
	captured_config JSON NOT NULL, 
	captured_targets JSON NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	version BIGINT NOT NULL, 
	restore_state JSON, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_maintenance_work_tenant UNIQUE (tenant_id, id), 
	CONSTRAINT fk_maintenance_work_program FOREIGN KEY(tenant_id, program_id) REFERENCES maintenance_programs (tenant_id, id), 
	CONSTRAINT fk_maintenance_work_order FOREIGN KEY(tenant_id, repair_order_id) REFERENCES repair_orders (tenant_id, id), 
	CONSTRAINT ck_maintenance_work_state CHECK (state IN ('active','pending_evidence','review_required','completed','detached')), 
	CONSTRAINT ck_maintenance_work_versions CHECK (cycle >= 1 AND version >= 1 AND program_version >= 1), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)
    """)
    op.execute('CREATE INDEX ix_maintenance_work_order ON maintenance_work_links (tenant_id, repair_order_id)')
    op.execute("CREATE UNIQUE INDEX uq_maintenance_work_claim ON maintenance_work_links (tenant_id, program_id, cycle) WHERE state IN ('active','pending_evidence','review_required')")
    op.execute("""
CREATE TABLE maintenance_operation_links (
	work_link_id UUID NOT NULL, 
	operation_id UUID NOT NULL, 
	identity_snapshot JSON NOT NULL, 
	version BIGINT NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID NOT NULL, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_maintenance_operation_tenant UNIQUE (tenant_id, id), 
	CONSTRAINT uq_maintenance_operation_identity UNIQUE (tenant_id, work_link_id, operation_id), 
	CONSTRAINT fk_maintenance_operation_work FOREIGN KEY(tenant_id, work_link_id) REFERENCES maintenance_work_links (tenant_id, id), 
	CONSTRAINT ck_maintenance_operation_state CHECK (state IN ('active','detached')),
	CONSTRAINT ck_maintenance_operation_version CHECK (version >= 1), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)
    """)
    op.execute('CREATE INDEX ix_maintenance_operation_lookup ON maintenance_operation_links (tenant_id, operation_id)')
    op.execute("""
CREATE TABLE maintenance_program_events (
	program_id UUID NOT NULL, 
	version BIGINT NOT NULL, 
	action VARCHAR(48) NOT NULL, 
	actor_id UUID, 
	reason VARCHAR(500), 
	before_values JSON NOT NULL, 
	after_values JSON NOT NULL, 
	id UUID NOT NULL, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_maintenance_event_tenant UNIQUE (tenant_id, id), 
	CONSTRAINT uq_maintenance_event_version UNIQUE (tenant_id, program_id, version), 
	CONSTRAINT fk_maintenance_event_program FOREIGN KEY(tenant_id, program_id) REFERENCES maintenance_programs (tenant_id, id), 
	CONSTRAINT ck_maintenance_event_version CHECK (version >= 1), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)
    """)
    op.execute("""
CREATE TABLE maintenance_completions (
	program_id UUID NOT NULL, 
	cycle BIGINT, 
	work_link_id UUID, 
	action VARCHAR(24) NOT NULL, 
	result VARCHAR(24) NOT NULL, 
	performed_on DATE, 
	readings JSON NOT NULL, 
	source_kind VARCHAR(24) NOT NULL, 
	source_id UUID, 
	source_fingerprint VARCHAR(64) NOT NULL, 
	source_snapshot JSON NOT NULL, 
	configuration JSON NOT NULL, 
	previous_targets JSON NOT NULL, 
	next_targets JSON NOT NULL, 
	supersedes_id UUID, 
	recognition_key VARCHAR(100), 
	actor_id UUID NOT NULL, 
	request_id UUID NOT NULL, 
	request_fingerprint VARCHAR(64) NOT NULL, 
	id UUID NOT NULL, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_maintenance_completion_tenant UNIQUE (tenant_id, id), 
	CONSTRAINT uq_maintenance_completion_source UNIQUE (tenant_id, program_id, recognition_key), 
	CONSTRAINT fk_maintenance_completion_program FOREIGN KEY(tenant_id, program_id) REFERENCES maintenance_programs (tenant_id, id), 
	CONSTRAINT fk_maintenance_completion_work FOREIGN KEY(tenant_id, work_link_id) REFERENCES maintenance_work_links (tenant_id, id), 
	CONSTRAINT fk_maintenance_completion_prior FOREIGN KEY(tenant_id, supersedes_id) REFERENCES maintenance_completions (tenant_id, id), 
	CONSTRAINT ck_maintenance_completion_action CHECK (action IN ('finalize','pending','resolve_pending','recognize','reaffirm','supersede','revoke')), 
	CONSTRAINT ck_maintenance_completion_work_identity CHECK (action NOT IN ('finalize','pending','resolve_pending') OR (work_link_id IS NOT NULL AND cycle IS NOT NULL AND cycle >= 1 AND source_kind='repair_order' AND source_id IS NOT NULL)),
	CONSTRAINT ck_maintenance_completion_recognition_identity CHECK (action != 'recognize' OR (source_kind IN ('repair_order','external_service') AND source_id IS NOT NULL)),
	CONSTRAINT ck_maintenance_completion_result CHECK (result IN ('advanced','pending_evidence','history_only','reaffirmed','revoked','review_required')), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)
    """)
    op.execute('CREATE INDEX ix_maintenance_completion_source ON maintenance_completions (tenant_id, source_kind, source_id)')
    op.execute("CREATE UNIQUE INDEX uq_maintenance_first_work_evidence ON maintenance_completions (tenant_id, work_link_id) WHERE action IN ('finalize','pending')")
    op.execute("CREATE UNIQUE INDEX uq_maintenance_work_resolution ON maintenance_completions (tenant_id, work_link_id) WHERE action='resolve_pending'")
    op.execute("CREATE UNIQUE INDEX uq_maintenance_source_program ON maintenance_completions (tenant_id, program_id, source_kind, source_id) WHERE action IN ('finalize','pending','recognize')")
    op.execute("""
CREATE TABLE maintenance_readings (
	vehicle_id UUID NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	odometer_miles INTEGER, 
	engine_hours NUMERIC(12, 2), 
	source VARCHAR(24) NOT NULL, 
	note VARCHAR(500), 
	actor_id UUID NOT NULL, 
	request_id UUID NOT NULL, 
	id UUID NOT NULL, 
	tenant_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_maintenance_reading_tenant UNIQUE (tenant_id, id), 
	CONSTRAINT uq_maintenance_reading_request UNIQUE (tenant_id, request_id), 
	CONSTRAINT fk_maintenance_reading_vehicle FOREIGN KEY(tenant_id, vehicle_id) REFERENCES vehicles (tenant_id, id), 
	CONSTRAINT ck_maintenance_reading_present CHECK (odometer_miles IS NOT NULL OR engine_hours IS NOT NULL), 
	CONSTRAINT ck_maintenance_reading_miles CHECK (odometer_miles IS NULL OR odometer_miles BETWEEN 0 AND 99999999), 
	CONSTRAINT ck_maintenance_reading_hours CHECK (engine_hours IS NULL OR (engine_hours >= 0 AND engine_hours <= 10000000)), 
	CONSTRAINT ck_maintenance_reading_source CHECK (source IN ('staff_observed','staff_reported')), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)
    """)
    op.execute('CREATE INDEX ix_maintenance_reading_vehicle ON maintenance_readings (tenant_id, vehicle_id, observed_at)')
    op.create_foreign_key('fk_maintenance_program_completion', 'maintenance_programs', 'maintenance_completions', ['tenant_id','controlling_completion_id'], ['tenant_id','id'])
    _admit_legacy()
    _protect_evidence()


def _insert(table, values):
    bind = op.get_bind()
    columns = ','.join(values)
    params = ','.join('CAST(:'+key+' AS JSON)' if isinstance(value, (dict, list)) else ':'+key for key,value in values.items())
    bind.execute(sa.text('INSERT INTO '+table+' ('+columns+') VALUES ('+params+')'),
                 {key:json.dumps(value, default=str) if isinstance(value,(dict,list)) else value for key,value in values.items()})


def _package(bind, tenant_id, rows):
    result=[]
    for row in rows:
        service=bind.execute(sa.text('SELECT id,name,is_active,deleted_at FROM services WHERE tenant_id=:tenant AND id=:id'), {'tenant':tenant_id,'id':row['service_id']}).mappings().first()
        result.append({'id':str(row['service_id']), 'name':service['name'] if service else 'Unavailable service',
                       'availability':'missing' if not service else 'active' if service['is_active'] and service['deleted_at'] is None else 'archived'})
    return result


def _admit_legacy():
    """Deterministic enrollment from explicit source records, never column defaults."""
    bind=op.get_bind()
    vehicles=bind.execute(sa.text('''SELECT v.* FROM vehicles v WHERE v.deleted_at IS NULL AND
      (v.next_pm_miles IS NOT NULL OR v.pm_due_date IS NOT NULL OR EXISTS
       (SELECT 1 FROM vehicle_pm_services p WHERE p.vehicle_id=v.id AND p.tenant_id=v.tenant_id AND p.deleted_at IS NULL) OR EXISTS
       (SELECT 1 FROM repair_orders r WHERE r.vehicle_id=v.id AND r.tenant_id=v.tenant_id AND r.is_pm IS TRUE AND r.deleted_at IS NULL)) ORDER BY v.tenant_id,v.id''')).mappings().all()
    for vehicle in vehicles:
        tenant,vid=vehicle['tenant_id'],vehicle['id']
        pid=uuid5(NAMESPACE,f'legacy:{tenant}:{vid}')
        if bind.execute(sa.text('SELECT 1 FROM maintenance_programs WHERE tenant_id=:tenant AND id=:id'), {'tenant':tenant,'id':pid}).scalar():
            continue
        stamp=datetime.now(timezone.utc)
        package_rows=bind.execute(sa.text('SELECT service_id FROM vehicle_pm_services WHERE tenant_id=:tenant AND vehicle_id=:id AND deleted_at IS NULL ORDER BY sort_order,id'), {'tenant':tenant,'id':vid}).mappings().all()
        package=_package(bind,tenant,package_rows)
        days=vehicle['pm_interval_days'];miles=vehicle['pm_interval_miles'];target_miles=vehicle['next_pm_miles']
        invalid=(days is not None and not 1<=days<=36500) or (miles is not None and not 1<=miles<=99999999) or (target_miles is not None and not 0<=target_miles<=99999999)
        codes=['legacy_invalid_interval'] if invalid else []
        active=bind.execute(sa.text('''SELECT id,order_number FROM repair_orders WHERE tenant_id=:tenant AND vehicle_id=:id AND is_pm IS TRUE AND deleted_at IS NULL
          AND status NOT IN ('completed','invoiced','paid','cancelled','declined') ORDER BY id'''), {'tenant':tenant,'id':vid}).mappings().all()
        mapped=[];work_package=[]
        if len(active)>1:
            codes.append('legacy_ambiguous_work')
        elif len(active)==1:
            rows=bind.execute(sa.text('SELECT service_id FROM repair_order_pm_services WHERE tenant_id=:tenant AND repair_order_id=:id AND deleted_at IS NULL ORDER BY sort_order,id'), {'tenant':tenant,'id':active[0]['id']}).mappings().all()
            if not rows:
                rows=package_rows
            work_package=_package(bind,tenant,rows)
            if not rows:
                codes.append('legacy_unmapped_work')
            else:
                for sid in dict.fromkeys(row['service_id'] for row in rows):
                    labor=bind.execute(sa.text('''SELECT id,source_service_id,description,execution_status,execution_version FROM labor
                      WHERE tenant_id=:tenant AND repair_order_id=:order AND source_service_id=:service AND deleted_at IS NULL ORDER BY id'''), {'tenant':tenant,'order':active[0]['id'],'service':sid}).mappings().all()
                    if len(labor)!=1:
                        codes.append('legacy_unmapped_work');break
                    mapped.append(labor[0])
        intervals={'days':days if days is not None and 1<=days<=36500 else None,'miles':miles if miles is not None and 1<=miles<=99999999 else None,'engine_hours':None}
        targets={'due_on':str(vehicle['pm_due_date']) if vehicle['pm_due_date'] else None,'odometer_miles':target_miles if target_miles is not None and 0<=target_miles<=99999999 else None,'engine_hours':None}
        provenance={'kind':'legacy','evidence_id':None,'confirmed_at':None}
        legacy={'pm_interval_days':days,'pm_interval_miles':miles,'next_pm_miles':target_miles,'pm_due_date':str(vehicle['pm_due_date']) if vehicle['pm_due_date'] else None,
                'date_rule':'600_miles_per_day_saturday','package':package,'active_pm_order_ids':[str(row['id']) for row in active]}
        _insert('maintenance_programs',{'id':pid,'tenant_id':tenant,'vehicle_id':vid,'name':'Preventive maintenance','version':1,'mode':'legacy',
            'interval_days':intervals['days'],'interval_miles':intervals['miles'],'interval_hours':None,'target_due_on':vehicle['pm_due_date'],'target_miles':targets['odometer_miles'],'target_hours':None,
            'target_provenance':provenance,'service_id':None,'service_snapshot':None,'legacy_package':package,'legacy_snapshot':legacy,
            'current_cycle':1,'baseline_generation':1,'baseline_snapshot':None,'controlling_completion_id':None,'review_codes':list(dict.fromkeys(codes)),
            'archived_at':None,'created_by':None,'updated_by':None,'created_at':stamp,'updated_at':stamp})
        after={'mode':'legacy','intervals':intervals,'targets':targets,'legacy_package':package,'legacy_snapshot':legacy,'review_codes':list(dict.fromkeys(codes))}
        if len(active)==1 and mapped and not codes:
            link_id=uuid5(NAMESPACE,f'legacy-work:{tenant}:{vid}:{active[0]["id"]}')
            config={'name':'Preventive maintenance','mode':'legacy','intervals':intervals,'service':None,'legacy_package':work_package,'baseline_generation':1,'legacy_snapshot':legacy}
            _insert('maintenance_work_links',{'id':link_id,'tenant_id':tenant,'program_id':pid,'cycle':1,'repair_order_id':active[0]['id'],'program_version':1,
                'captured_config':config,'captured_targets':targets,'state':'active','version':1,'restore_state':None,'created_at':stamp,'updated_at':stamp})
            for labor in mapped:
                _insert('maintenance_operation_links',{'id':uuid5(NAMESPACE,f'legacy-op:{link_id}:{labor["id"]}'),'tenant_id':tenant,'work_link_id':link_id,'operation_id':labor['id'],
                    'version':1,'identity_snapshot':{'operation_id':str(labor['id']),'service_id':str(labor['source_service_id']),'description':labor['description'],'execution_version':labor['execution_version'],'legacy':True},
                    'state':'active','created_at':stamp,'updated_at':stamp})
            after['work_link']={'id':str(link_id),'version':1,'state':'active'}
        _insert('maintenance_program_events',{'id':uuid5(NAMESPACE,f'legacy-event:{tenant}:{vid}'),'tenant_id':tenant,'program_id':pid,'version':1,'action':'legacy_admitted',
            'actor_id':None,'reason':None,'before_values':{},'after_values':after,'created_at':stamp})


def _protect_evidence():
    op.execute('''CREATE FUNCTION db134_immutable_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'DB134 maintenance evidence is immutable'; END; $$''')
    for table in ('maintenance_program_events','maintenance_completions','maintenance_readings'):
        op.execute(f'CREATE TRIGGER trg_db134_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION db134_immutable_evidence()')
    op.execute('''CREATE FUNCTION db134_program_identity() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id OR OLD.vehicle_id IS DISTINCT FROM NEW.vehicle_id OR OLD.id IS DISTINCT FROM NEW.id
      THEN RAISE EXCEPTION 'DB134 program identity is immutable'; END IF;
      IF NEW.version <> OLD.version+1 THEN RAISE EXCEPTION 'DB134 program mutation requires next version'; END IF;
      RETURN NEW; END; $$''')
    op.execute('CREATE TRIGGER trg_db134_program_identity BEFORE UPDATE ON maintenance_programs FOR EACH ROW EXECUTE FUNCTION db134_program_identity()')
    op.execute('''CREATE FUNCTION db134_work_identity() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.id IS DISTINCT FROM NEW.id OR OLD.tenant_id IS DISTINCT FROM NEW.tenant_id OR OLD.program_id IS DISTINCT FROM NEW.program_id OR OLD.cycle IS DISTINCT FROM NEW.cycle OR
         OLD.repair_order_id IS DISTINCT FROM NEW.repair_order_id OR OLD.program_version IS DISTINCT FROM NEW.program_version OR
         OLD.captured_config::jsonb IS DISTINCT FROM NEW.captured_config::jsonb OR OLD.captured_targets::jsonb IS DISTINCT FROM NEW.captured_targets::jsonb
      THEN RAISE EXCEPTION 'DB134 work identity is immutable'; END IF;
      IF NEW.version <> OLD.version+1 THEN RAISE EXCEPTION 'DB134 work mutation requires next version'; END IF;
      RETURN NEW; END; $$''')
    op.execute('CREATE TRIGGER trg_db134_work_identity BEFORE UPDATE ON maintenance_work_links FOR EACH ROW EXECUTE FUNCTION db134_work_identity()')
    op.execute('''CREATE FUNCTION db134_operation_identity() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF OLD.id IS DISTINCT FROM NEW.id OR OLD.tenant_id IS DISTINCT FROM NEW.tenant_id OR OLD.work_link_id IS DISTINCT FROM NEW.work_link_id OR OLD.operation_id IS DISTINCT FROM NEW.operation_id OR
        OLD.identity_snapshot::jsonb IS DISTINCT FROM NEW.identity_snapshot::jsonb
      THEN RAISE EXCEPTION 'DB134 operation identity is immutable'; END IF;
      IF NEW.version <> OLD.version+1 THEN RAISE EXCEPTION 'DB134 operation mutation requires next version'; END IF;
      RETURN NEW; END; $$''')
    op.execute('CREATE TRIGGER trg_db134_operation_identity BEFORE UPDATE ON maintenance_operation_links FOR EACH ROW EXECUTE FUNCTION db134_operation_identity()')
    op.execute('''CREATE FUNCTION db134_program_event_required() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF NOT EXISTS(SELECT 1 FROM maintenance_program_events WHERE tenant_id=NEW.tenant_id AND program_id=NEW.id AND version=NEW.version)
      THEN RAISE EXCEPTION 'DB134 program event is required'; END IF; RETURN NEW; END; $$''')
    op.execute('''CREATE CONSTRAINT TRIGGER trg_db134_program_event AFTER INSERT OR UPDATE ON maintenance_programs
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION db134_program_event_required()''')
    op.execute('''CREATE FUNCTION db134_work_event_required() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF NOT EXISTS(SELECT 1 FROM maintenance_program_events WHERE tenant_id=NEW.tenant_id AND program_id=NEW.program_id
        AND after_values->'work_link'->>'id'=NEW.id::text AND after_values->'work_link'->>'version'=NEW.version::text)
      THEN RAISE EXCEPTION 'DB134 work event is required'; END IF; RETURN NEW; END; $$''')
    op.execute('''CREATE CONSTRAINT TRIGGER trg_db134_work_event AFTER INSERT OR UPDATE ON maintenance_work_links
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION db134_work_event_required()''')

    op.execute("""CREATE FUNCTION db134_operation_event_required() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      IF NOT EXISTS(SELECT 1 FROM maintenance_program_events e JOIN maintenance_work_links w
        ON w.tenant_id=e.tenant_id AND w.program_id=e.program_id
        WHERE w.tenant_id=NEW.tenant_id AND w.id=NEW.work_link_id
          AND e.after_values->'operation_versions'->>NEW.id::text=NEW.version::text)
      THEN RAISE EXCEPTION 'DB134 operation event is required'; END IF; RETURN NEW; END; $$""")
    op.execute("""CREATE CONSTRAINT TRIGGER trg_db134_operation_event AFTER INSERT OR UPDATE ON maintenance_operation_links
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION db134_operation_event_required()""")
    for table in ('maintenance_programs','maintenance_work_links','maintenance_operation_links'):
        op.execute('CREATE TRIGGER trg_db134_retain_'+table+' BEFORE DELETE ON '+table+' FOR EACH ROW EXECUTE FUNCTION db134_immutable_evidence()')


def downgrade():
    op.execute('''DO $$ BEGIN IF EXISTS(SELECT 1 FROM maintenance_programs) OR EXISTS(SELECT 1 FROM maintenance_readings)
      THEN RAISE EXCEPTION 'DB134 downgrade refused: maintenance identity or evidence exists'; END IF; END $$''')
    op.drop_constraint('fk_maintenance_program_completion','maintenance_programs',type_='foreignkey')
    for table in ('maintenance_readings','maintenance_completions','maintenance_program_events','maintenance_operation_links','maintenance_work_links','maintenance_programs'):
        op.drop_table(table)
    op.drop_index('uq_repair_orders_tenant_identity', table_name='repair_orders')
    for function in ('db134_operation_event_required','db134_work_event_required','db134_program_event_required','db134_operation_identity','db134_work_identity','db134_program_identity','db134_immutable_evidence'):
        op.execute('DROP FUNCTION '+function+'()')
