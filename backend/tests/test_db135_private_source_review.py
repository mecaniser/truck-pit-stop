import hashlib
import json
import stat

import pytest

from scripts.db135_private_source_review import save_private_review


def test_private_review_creates_exclusive_0600_file(tmp_path):
    target = tmp_path / "review.json"
    report = {"read_only": True, "invoice_count": 1, "rows": [{"disposition": "unresolved"}]}
    digest = save_private_review(target, report)
    payload = target.read_bytes()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert digest == hashlib.sha256(payload).hexdigest()
    assert json.loads(payload) == report
    with pytest.raises(FileExistsError):
        save_private_review(target, report)
    assert target.read_bytes() == payload


def test_private_review_refuses_non_readonly_or_symlink(tmp_path):
    target = tmp_path / "review.json"
    with pytest.raises(ValueError, match="read-only"):
        save_private_review(target, {"read_only": False})
    assert not target.exists()
    outside = tmp_path / "outside"
    outside.write_text("unchanged")
    target.symlink_to(outside)
    with pytest.raises(FileExistsError):
        save_private_review(target, {"read_only": True})
    assert outside.read_text() == "unchanged"
