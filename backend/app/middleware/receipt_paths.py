"""Exact private receipt route boundary shared by ingress middleware."""
import re

# Match the router's identity segments, not only canonical UUID spellings:
# FastAPI also accepts compact/URN UUIDs, and validation errors remain private.
_IDENTITY = r"[^/]+"
_PATH = re.compile(rf"/api/v1/vehicles/{_IDENTITY}/external-services/{_IDENTITY}/receipts(?:/{_IDENTITY}/(?:remove|restore|history|download))?/?\Z")


def is_receipt_path(path: str) -> bool:
    return _PATH.fullmatch(path) is not None
