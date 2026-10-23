"""Submit a benign synthetic job twice to the private worker and verify one receipt."""
import json
from db_worker import database_probe
first = database_probe.apply_async(args=['synthetic-db-probe-v1'], queue='db-local-test').get(timeout=30)
second = database_probe.apply_async(args=['synthetic-db-probe-v1'], queue='db-local-test').get(timeout=30)
assert first == second and first['customers'] == 2 and first['execution_count'] == 1
print(json.dumps({'first': first, 'replay': second, 'receipt_idempotent': True}))
