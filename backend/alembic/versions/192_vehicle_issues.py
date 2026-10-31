"""Standalone tenant-scoped truck issue metadata; no source data rewrite."""

from alembic import op
import sqlalchemy as sa

revision = "192_vehicle_issues"
down_revision = "191_fuel_reviewed_binding"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE vehicle_issues (
    tenant_id UUID NOT NULL,
    vehicle_id UUID NOT NULL,
    description TEXT NOT NULL,
    priority VARCHAR(16) DEFAULT 'soon' NOT NULL,
    state VARCHAR(16) DEFAULT 'open' NOT NULL,
    responsible_user_id UUID,
    follow_up_on DATE,
    state_reason VARCHAR(1000),
    state_changed_at TIMESTAMP WITH TIME ZONE,
    state_changed_by UUID,
    created_by UUID NOT NULL,
    version INTEGER DEFAULT '1' NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_vehicle_issues_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_vehicle_issues_vehicle_id UNIQUE (tenant_id, vehicle_id, id),
    CONSTRAINT fk_vehicle_issues_vehicle FOREIGN KEY(tenant_id, vehicle_id) REFERENCES vehicles (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_vehicle_issues_priority CHECK (priority IN ('urgent','soon','monitor')),
    CONSTRAINT ck_vehicle_issues_state CHECK (state IN ('open','resolved','dismissed')),
    CONSTRAINT ck_vehicle_issues_version CHECK (version >= 1),
    CONSTRAINT ck_vehicle_issues_description CHECK (length(trim(description)) BETWEEN 1 AND 2000),
    FOREIGN KEY(tenant_id) REFERENCES tenants (id),
    FOREIGN KEY(responsible_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(state_changed_by) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT
)

""")
    op.execute("""CREATE INDEX ix_vehicle_issues_id ON vehicle_issues (id)""")
    op.execute(
        """CREATE INDEX ix_vehicle_issues_queue ON vehicle_issues (tenant_id, vehicle_id, state, priority, follow_up_on, created_at, id)"""
    )
    op.execute("""
CREATE TABLE vehicle_issue_links (
    tenant_id UUID NOT NULL,
    vehicle_id UUID NOT NULL,
    issue_id UUID NOT NULL,
    target_order_id UUID NOT NULL,
    order_number VARCHAR(50) NOT NULL,
    created_by UUID NOT NULL,
    ended_at TIMESTAMP WITH TIME ZONE,
    ended_by UUID,
    end_reason VARCHAR(1000),
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_vehicle_issue_links_identity UNIQUE (tenant_id, issue_id, id),
    CONSTRAINT fk_vehicle_issue_links_issue FOREIGN KEY(tenant_id, vehicle_id, issue_id) REFERENCES vehicle_issues (tenant_id, vehicle_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_vehicle_issue_links_order FOREIGN KEY(tenant_id, target_order_id) REFERENCES repair_orders (tenant_id, id) ON DELETE RESTRICT,
    FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(ended_by) REFERENCES users (id) ON DELETE RESTRICT
)

""")
    op.execute("""CREATE INDEX ix_vehicle_issue_links_id ON vehicle_issue_links (id)""")
    op.execute(
        """CREATE UNIQUE INDEX uq_vehicle_issue_current_link ON vehicle_issue_links (tenant_id, issue_id) WHERE ended_at IS NULL"""
    )
    op.execute("""
CREATE TABLE vehicle_issue_requests (
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    operation VARCHAR(20) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    issue_id UUID NOT NULL,
    link_id UUID,
    accepted_version INTEGER NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_vehicle_issue_request UNIQUE (tenant_id, request_id),
    CONSTRAINT fk_vehicle_issue_request_issue FOREIGN KEY(tenant_id, issue_id) REFERENCES vehicle_issues (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_vehicle_issue_request_link FOREIGN KEY(tenant_id, issue_id, link_id) REFERENCES vehicle_issue_links (tenant_id, issue_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_vehicle_issue_request_version CHECK (accepted_version >= 1),
    FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE RESTRICT
)

""")
    op.execute(
        """CREATE INDEX ix_vehicle_issue_requests_id ON vehicle_issue_requests (id)"""
    )
    op.execute("""
CREATE TABLE vehicle_issue_events (
    tenant_id UUID NOT NULL,
    issue_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    operation VARCHAR(20) NOT NULL,
    version INTEGER NOT NULL,
    changes JSON NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT fk_vehicle_issue_event_issue FOREIGN KEY(tenant_id, issue_id) REFERENCES vehicle_issues (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT uq_vehicle_issue_event_version UNIQUE (tenant_id, issue_id, version),
    CONSTRAINT ck_vehicle_issue_event_version CHECK (version >= 1),
    FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE RESTRICT
)

""")
    op.execute(
        """CREATE INDEX ix_vehicle_issue_events_id ON vehicle_issue_events (id)"""
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM vehicle_issues LIMIT 1")).first():
        raise RuntimeError("Truck issue history exists; retain its metadata and schema")
    op.drop_table("vehicle_issue_events")
    op.drop_table("vehicle_issue_requests")
    op.drop_table("vehicle_issue_links")
    op.drop_table("vehicle_issues")
