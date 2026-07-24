"""Fail CI when the migration graph has anything other than one head."""
from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()

    if len(heads) != 1:
        print("Alembic migration graph must have exactly one head.", file=sys.stderr)
        print(f"Found {len(heads)} heads: {', '.join(heads) or '(none)'}", file=sys.stderr)
        print(
            "Rebase onto main, then create an Alembic merge revision if the branches are both required.",
            file=sys.stderr,
        )
        return 1

    revision = script.get_revision(heads[0])
    print(f"Alembic graph is linear at head {heads[0]} ({revision.doc if revision else 'unknown'}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
