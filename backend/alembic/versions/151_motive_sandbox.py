"""Add the disabled Motive fixture account and tenant-scoped telemetry storage."""

from alembic import op

revision = "151_motive_sandbox"
down_revision = "150_pm_saturday_service_day"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_vehicles_tenant_id", "vehicles", ["tenant_id", "id"]
    )
    op.execute("""
CREATE TABLE motive_accounts (
	tenant_id UUID NOT NULL,
	provider VARCHAR(16) DEFAULT 'motive' NOT NULL,
	mode VARCHAR(16) DEFAULT 'fixture' NOT NULL,
	external_company_id VARCHAR(120) NOT NULL,
	enabled BOOLEAN DEFAULT 'false' NOT NULL,
	connection_state VARCHAR(32) DEFAULT 'fixture' NOT NULL,
	granted_scopes JSON NOT NULL,
	last_successful_sync_at TIMESTAMP WITH TIME ZONE,
	last_sample_sequence BIGINT DEFAULT '0' NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT uq_motive_accounts_tenant_id UNIQUE (tenant_id, id),
	CONSTRAINT uq_motive_accounts_tenant_provider UNIQUE (tenant_id, provider),
	CONSTRAINT ck_motive_fixture_only CHECK (provider = 'motive' AND mode = 'fixture'),
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
)
""")
    op.execute("CREATE INDEX ix_motive_accounts_id ON motive_accounts (id)")
    op.execute("""
CREATE TABLE motive_bindings (
	tenant_id UUID NOT NULL,
	account_id UUID NOT NULL,
	vehicle_id UUID NOT NULL,
	provider_vehicle_id VARCHAR(120) NOT NULL,
	gateway_id VARCHAR(120),
	valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
	valid_to TIMESTAMP WITH TIME ZONE,
	match_basis VARCHAR(32) NOT NULL,
	verification_state VARCHAR(16) NOT NULL,
	verified_by_user_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT uq_motive_bindings_identity UNIQUE (tenant_id, account_id, id),
	CONSTRAINT fk_motive_binding_account FOREIGN KEY(tenant_id, account_id) REFERENCES motive_accounts (tenant_id, id),
	CONSTRAINT fk_motive_binding_vehicle FOREIGN KEY(tenant_id, vehicle_id) REFERENCES vehicles (tenant_id, id),
	CONSTRAINT ck_motive_binding_interval CHECK (valid_to IS NULL OR valid_to > valid_from),
	FOREIGN KEY(verified_by_user_id) REFERENCES users (id)
)
""")
    op.execute("CREATE INDEX ix_motive_bindings_id ON motive_bindings (id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_motive_binding_open_external ON motive_bindings (account_id, provider_vehicle_id) WHERE valid_to IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_motive_binding_open_gateway ON motive_bindings (account_id, gateway_id) WHERE valid_to IS NULL AND gateway_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_motive_binding_open_vehicle ON motive_bindings (tenant_id, vehicle_id) WHERE valid_to IS NULL"
    )
    op.execute("""
CREATE TABLE motive_location_samples (
	tenant_id UUID NOT NULL,
	account_id UUID NOT NULL,
	binding_id UUID NOT NULL,
	event_id VARCHAR(120) NOT NULL,
	located_at TIMESTAMP WITH TIME ZONE NOT NULL,
	received_at TIMESTAMP WITH TIME ZONE NOT NULL,
	ingestion_sequence BIGINT NOT NULL,
	lat FLOAT NOT NULL,
	lng FLOAT NOT NULL,
	speed_mph FLOAT,
	bearing_degrees FLOAT,
	virtual_odometer_miles FLOAT,
	engine_hours FLOAT,
	source_type VARCHAR(32) NOT NULL,
	payload_sha256 VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT uq_motive_sample_event UNIQUE (account_id, event_id),
	CONSTRAINT uq_motive_sample_sequence UNIQUE (account_id, ingestion_sequence),
	CONSTRAINT uq_motive_sample_identity UNIQUE (tenant_id, account_id, id),
	CONSTRAINT fk_motive_sample_binding FOREIGN KEY(tenant_id, account_id, binding_id) REFERENCES motive_bindings (tenant_id, account_id, id),
	CONSTRAINT ck_motive_coordinates CHECK (lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180)
)
""")
    op.execute(
        "CREATE INDEX ix_motive_location_samples_id ON motive_location_samples (id)"
    )
    op.execute(
        "CREATE INDEX ix_motive_sample_latest ON motive_location_samples (tenant_id, binding_id, located_at, ingestion_sequence)"
    )
    op.execute("""
CREATE TABLE motive_ingestion_receipts (
	tenant_id UUID NOT NULL,
	account_id UUID NOT NULL,
	event_id VARCHAR(120),
	sample_id UUID,
	received_at TIMESTAMP WITH TIME ZONE NOT NULL,
	signature_state VARCHAR(16) NOT NULL,
	payload_sha256 VARCHAR(64) NOT NULL,
	content_sha256 VARCHAR(64),
	outcome VARCHAR(24) NOT NULL,
	reason VARCHAR(32),
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT fk_motive_receipt_account FOREIGN KEY(tenant_id, account_id) REFERENCES motive_accounts (tenant_id, id),
	CONSTRAINT fk_motive_receipt_sample FOREIGN KEY(tenant_id, account_id, sample_id) REFERENCES motive_location_samples (tenant_id, account_id, id)
)
""")
    op.execute(
        "CREATE INDEX ix_motive_ingestion_receipts_id ON motive_ingestion_receipts (id)"
    )
    op.execute(
        "CREATE INDEX ix_motive_receipt_retention ON motive_ingestion_receipts (tenant_id, received_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_motive_receipt_first_event ON motive_ingestion_receipts (account_id, event_id) WHERE outcome = 'stored'"
    )


def downgrade():
    op.drop_table("motive_ingestion_receipts")
    op.drop_table("motive_location_samples")
    op.drop_table("motive_bindings")
    op.drop_table("motive_accounts")
    op.drop_constraint("uq_vehicles_tenant_id", "vehicles", type_="unique")
