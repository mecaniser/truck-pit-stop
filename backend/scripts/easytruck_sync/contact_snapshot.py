"""Compatibility imports for the standalone ETS collector/importer."""
from pathlib import Path
import sys

# Direct CLI execution starts with the collector directory on sys.path.
_BACKEND_ROOT = str(Path(__file__).resolve().parents[2])
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.services.account_contact_snapshot import (  # noqa: E402,F401
    normalize, latest, for_history, digest, instant, phone, REASONS
)
