"""Decide whether a pull request can omit backend pytest jobs.

Only a frontend change, optionally accompanied by documentation, qualifies.
Unknown paths and inspection failures deliberately require the backend suites.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath


def backend_required(paths: list[str]) -> bool:
    if not paths or not any(path.startswith("frontend/") for path in paths):
        return True
    return any(
        not (
            path.startswith("frontend/")
            or path.startswith("docs/")
            or ("/" not in path and path.endswith(".md"))
        )
        for path in paths
    )


def changed_paths(base: str, head: str) -> list[str]:
    merge_base = subprocess.check_output(["git", "merge-base", base, head], text=True).strip()
    # --no-renames exposes both sides of moves, including a deleted backend file.
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "-z", "--no-renames", merge_base, head]
    )
    paths = [item.decode("utf-8") for item in output.split(b"\0") if item]
    if any(PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts for path in paths):
        raise ValueError("unexpected changed path")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    try:
        paths = changed_paths(args.base, args.head)
        required = backend_required(paths)
        reason = "backend or shared change" if required else "frontend and documentation only"
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError, ValueError) as error:
        paths = []
        required = True
        reason = f"scope unavailable ({type(error).__name__}); fail closed"
    print(f"backend_required={'true' if required else 'false'}")
    print(f"reason={reason}")
    print(f"changed_paths={len(paths)}")


if __name__ == "__main__":
    main()
