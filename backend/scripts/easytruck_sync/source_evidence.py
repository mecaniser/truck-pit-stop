"""Compatibility imports for the standalone ETS collector/importer."""
from pathlib import Path
import sys

# Direct CLI execution starts with the collector directory on sys.path.
_BACKEND_ROOT = str(Path(__file__).resolve().parents[2])
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.services.ets_source_evidence import (  # noqa: E402,F401
    normalize_source_evidence, append_source_evidence, latest_source_evidence
)
