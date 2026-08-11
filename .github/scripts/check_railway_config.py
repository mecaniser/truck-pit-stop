#!/usr/bin/env python3
"""Keep Railway web cutovers health-gated without touching worker scope."""

import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPOSITORY_ROOT / "railway.json"


def main() -> int:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG

    try:
        config = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        print(f"Invalid Railway configuration: {error}", file=sys.stderr)
        return 1

    deploy = config.get("deploy", {})
    expected = {
        "healthcheckPath": "/health",
        "healthcheckTimeout": 300,
    }
    mismatches = [
        f"deploy.{key} must be {value!r}, got {deploy.get(key)!r}"
        for key, value in expected.items()
        if deploy.get(key) != value
    ]

    if mismatches:
        print("Railway deployment readiness check failed:", file=sys.stderr)
        for mismatch in mismatches:
            print(f"- {mismatch}", file=sys.stderr)
        return 1

    print("Railway deployment readiness check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
