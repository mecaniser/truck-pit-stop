from app.core.request_performance import (
    begin_request_database_stats,
    end_request_database_stats,
    record_database_query,
    sql_operation,
)
from app.db.models.customer_read_model import CustomerReadModel


def test_request_database_stats_accumulate_only_inside_a_request_context():
    record_database_query(99, "select")

    token = begin_request_database_stats()
    record_database_query(12.25, "select")
    record_database_query(3.5, "update")
    stats = end_request_database_stats(token)

    assert stats.query_count == 2
    assert stats.total_duration_ms == 15.75
    assert stats.slowest_duration_ms == 12.25
    assert stats.slowest_operation == "select"


def test_sql_operation_has_bounded_labels():
    assert sql_operation(" SELECT * FROM customers") == "select"
    assert sql_operation("UPDATE customers SET name = ?") == "update"
    assert sql_operation("WITH rows AS (SELECT 1) SELECT * FROM rows") == "other"


def test_customer_read_model_is_registered_for_schema_creation():
    assert CustomerReadModel.__tablename__ == "customer_read_models"
