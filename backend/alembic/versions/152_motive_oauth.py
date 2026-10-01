"""DB-036 company-scoped Motive OAuth connector.

Frozen additive schema; fixture151 remains unchanged.
"""
from alembic import op

revision = "152_motive_oauth"
down_revision = "151_motive_sandbox"
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE TABLE motive_connections (\n\ttenant_id UUID NOT NULL, \n\tfleet_customer_id UUID NOT NULL, \n\tprovider_company_id VARCHAR(120), \n\tprovider_company_name VARCHAR(255), \n\tstatus VARCHAR(32) NOT NULL, \n\tgeneration INTEGER NOT NULL, \n\tencrypted_tokens TEXT, \n\ttoken_key_version VARCHAR(32), \n\ttoken_expires_at TIMESTAMP WITH TIME ZONE, \n\tscopes VARCHAR(500) NOT NULL, \n\tconnected_at TIMESTAMP WITH TIME ZONE, \n\tlast_sync_at TIMESTAMP WITH TIME ZONE, \n\tnext_sync_at TIMESTAMP WITH TIME ZONE, \n\tlast_error_code VARCHAR(40), \n\tlast_sync_counts JSON, \n\tfailure_count INTEGER NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_motive_connection_company UNIQUE (tenant_id, fleet_customer_id), \n\tCONSTRAINT uq_motive_connection_identity UNIQUE (tenant_id, id), \n\tCONSTRAINT uq_motive_provider_company UNIQUE (tenant_id, provider_company_id), \n\tFOREIGN KEY(tenant_id, fleet_customer_id) REFERENCES customers (tenant_id, id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id)\n)')
    op.execute('CREATE INDEX ix_motive_connections_id ON motive_connections (id)')
    op.execute('CREATE TABLE motive_authorizations (\n\ttenant_id UUID NOT NULL, \n\tconnection_id UUID NOT NULL, \n\tuser_id UUID NOT NULL, \n\tstate_hash VARCHAR(64) NOT NULL, \n\tsession_hash VARCHAR(64) NOT NULL, \n\tgeneration INTEGER NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tconsumed_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id, connection_id) REFERENCES motive_connections (tenant_id, id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tUNIQUE (state_hash)\n)')
    op.execute('CREATE INDEX ix_motive_authorizations_id ON motive_authorizations (id)')
    op.execute('CREATE TABLE motive_remote_vehicles (\n\ttenant_id UUID NOT NULL, \n\tconnection_id UUID NOT NULL, \n\tprovider_vehicle_id VARCHAR(120) NOT NULL, \n\tnumber VARCHAR(120), \n\tvin VARCHAR(17), \n\tvehicle_id UUID, \n\tmapped_by_user_id UUID, \n\tmapped_at TIMESTAMP WITH TIME ZONE, \n\tlocated_at TIMESTAMP WITH TIME ZONE, \n\treceived_at TIMESTAMP WITH TIME ZONE, \n\tlat FLOAT, \n\tlng FLOAT, \n\tspeed_mph FLOAT, \n\tbearing FLOAT, \n\tdiscovered_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_motive_remote_vehicle UNIQUE (connection_id, provider_vehicle_id), \n\tCONSTRAINT uq_motive_remote_mapping UNIQUE (tenant_id, vehicle_id), \n\tFOREIGN KEY(tenant_id, connection_id) REFERENCES motive_connections (tenant_id, id), \n\tFOREIGN KEY(tenant_id, vehicle_id) REFERENCES vehicles (tenant_id, id), \n\tFOREIGN KEY(mapped_by_user_id) REFERENCES users (id)\n)')
    op.execute('CREATE INDEX ix_motive_remote_vehicles_id ON motive_remote_vehicles (id)')


def downgrade():
    op.drop_table('motive_remote_vehicles')
    op.drop_table('motive_authorizations')
    op.drop_table('motive_connections')
