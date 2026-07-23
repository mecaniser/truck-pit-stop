from __future__ import annotations

import pytest

from app.commands import schema_preflight


class FakeInspector:
    def __init__(
        self,
        *,
        include_source_line: bool = True,
        include_active_list_index: bool = True,
        include_provider_outbox: bool = True,
        include_quickbooks_webhook_deleted_at: bool = True,
    ):
        self.include_source_line = include_source_line
        self.include_active_list_index = include_active_list_index
        self.include_provider_outbox = include_provider_outbox
        self.include_quickbooks_webhook_deleted_at = include_quickbooks_webhook_deleted_at

    def get_columns(self, table_name: str):
        if table_name == "parts_usage":
            columns = [{"name": "id"}]
            if self.include_source_line:
                columns.append({"name": "source_line_id"})
            return columns
        if table_name == "provider_outbox":
            if not self.include_provider_outbox:
                return [{"name": "id"}]
            return [
                {"name": column}
                for column in (
                    "id", "tenant_id", "event_type", "aggregate_type", "aggregate_id",
                    "payload", "idempotency_key", "status", "attempt_count", "available_at",
                    "locked_until",
                )
            ]
        assert table_name == "quickbooks_webhook_events"
        columns = [{"name": "id"}]
        if self.include_quickbooks_webhook_deleted_at:
            columns.append({"name": "deleted_at"})
        return columns

    def get_indexes(self, table_name: str):
        if table_name == "parts_usage":
            return [
                {
                    "name": schema_preflight.PARTS_USAGE_SOURCE_LINE_INDEX,
                    "column_names": ["source_line_id"],
                }
            ]
        if table_name == "repair_orders":
            if not self.include_active_list_index:
                return []
            return [
                {
                    "name": schema_preflight.REPAIR_ORDER_ACTIVE_LIST_INDEX,
                    "column_names": ["tenant_id", "created_at"],
                }
            ]
        assert table_name == "provider_outbox"
        if not self.include_provider_outbox:
            return []
        return [
            {
                "name": schema_preflight.PROVIDER_OUTBOX_DUE_INDEX,
                "column_names": ["status", "available_at"],
            }
        ]

    def get_foreign_keys(self, table_name: str):
        assert table_name == "parts_usage"
        return [
            {
                "name": schema_preflight.PARTS_USAGE_SOURCE_LINE_FOREIGN_KEY,
                "constrained_columns": ["source_line_id"],
                "referred_table": "labor",
                "referred_columns": ["id"],
                "options": {"ondelete": "SET NULL"},
            }
        ]


def test_collect_schema_issues_accepts_required_objects():
    assert schema_preflight.collect_schema_issues(FakeInspector()) == []


def test_collect_schema_issues_reports_missing_column_and_list_index():
    issues = schema_preflight.collect_schema_issues(
        FakeInspector(include_source_line=False, include_active_list_index=False)
    )

    assert "missing required column parts_usage.source_line_id" in issues
    assert any("active repair-order list index" in issue for issue in issues)


def test_collect_schema_issues_reports_missing_provider_outbox_objects():
    issues = schema_preflight.collect_schema_issues(FakeInspector(include_provider_outbox=False))

    assert any("provider_outbox columns" in issue for issue in issues)
    assert any("provider outbox due index" in issue for issue in issues)


def test_collect_schema_issues_reports_missing_quickbooks_webhook_soft_delete_column():
    issues = schema_preflight.collect_schema_issues(
        FakeInspector(include_quickbooks_webhook_deleted_at=False)
    )

    assert "missing required column quickbooks_webhook_events.deleted_at" in issues


def test_verify_database_fails_when_live_revision_is_not_the_script_head(monkeypatch):
    class FakeContext:
        def get_current_heads(self):
            return ("080",)

    monkeypatch.setattr(
        schema_preflight.MigrationContext,
        "configure",
        lambda connection: FakeContext(),
    )
    monkeypatch.setattr(schema_preflight, "inspect", lambda connection: FakeInspector())

    with pytest.raises(schema_preflight.SchemaPreflightError) as exc_info:
        schema_preflight.verify_database(object(), {"081"})

    assert exc_info.value.issues == ("Alembic revision mismatch (expected 081; found 080)",)


def test_main_does_not_echo_database_url_on_connection_failure(monkeypatch, capsys):
    secret_url = "postgresql://private-user:private-password@private-host/private-db"
    monkeypatch.setenv("DATABASE_URL", secret_url)

    def fail_preflight(database_url: str):
        assert database_url == secret_url
        raise schema_preflight.SQLAlchemyError("connection failed")

    monkeypatch.setattr(schema_preflight, "run_preflight", fail_preflight)

    assert schema_preflight.main() == 1
    output = capsys.readouterr().err
    assert "unable to inspect" in output
    assert secret_url not in output
    assert "private-password" not in output
