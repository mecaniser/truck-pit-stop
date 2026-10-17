"""Production workers must not depend on the collector's script namespace."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


BACKEND = Path(__file__).resolve().parents[1]


def test_outcome_modules_import_with_only_application_package(tmp_path):
    shutil.copytree(BACKEND / "app", tmp_path / "app", ignore=shutil.ignore_patterns("__pycache__"))
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    code = """
import importlib.util
assert importlib.util.find_spec('scripts') is None
from app.services import ets_completed_outcome_source, native_completed_outcome_source
from app.services import shop_history_source, paid_invoice_webhook_service
from app.services.account_contact_snapshot import for_history
assert for_history(None, customer_id=None, dbn_customer_id=None, shop_id=None, source=None) is None
"""
    subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, check=True, capture_output=True, text=True)


def test_standalone_collector_compatibility_imports(tmp_path):
    collector = BACKEND / "scripts" / "easytruck_sync"
    code = """
from contact_snapshot import normalize, latest, for_history, digest
from source_evidence import normalize_source_evidence, append_source_evidence, latest_source_evidence
assert callable(latest_source_evidence)
"""
    subprocess.run([sys.executable, "-c", code], cwd=collector,
                   env={**os.environ, "PYTHONPATH": ""}, check=True, capture_output=True, text=True)
