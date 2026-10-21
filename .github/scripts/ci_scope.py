"""Conservatively scope PR suites; unknown paths require all application checks.

Only frontend source/assets and Markdown documentation qualify for reduced suites.
The workflow executes this classifier from the protected base, not PR code.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath


def classify(paths: list[str]) -> dict[str, bool]:
    full = {"backend_required": True, "frontend_required": True, "smoke_required": True}
    if not paths or any(
        PurePosixPath(path).is_absolute()
        or ".." in PurePosixPath(path).parts
        or "\\" in path
        or any(ord(char) < 32 for char in path)
        for path in paths
    ):
        return full

    def documentation(path: str) -> bool:
        return path.endswith(".md") and (path.startswith("docs/") or "/" not in path)

    if all(documentation(path) for path in paths):
        return {key: False for key in full}
    # Dependencies, build/test tools and configuration can affect shared CI or
    # API integration. Only application source/assets qualify as UI-only.
    def frontend_ui(path: str) -> bool:
        return path.startswith(("frontend/src/", "frontend/public/")) or path == "frontend/index.html"

    if all(frontend_ui(path) or documentation(path) for path in paths):
        return {**full, "backend_required": False}
    return full


def backend_required(paths: list[str]) -> bool:
    return classify(paths)["backend_required"]


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
        scope = classify(paths)
        reason = "backend or shared change" if scope["backend_required"] else (
            "frontend and Markdown documentation only" if scope["frontend_required"] else "Markdown documentation only"
        )
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError, ValueError) as error:
        paths = []
        scope = classify([])
        reason = f"scope unavailable ({type(error).__name__}); fail closed"
    for key, required in scope.items():
        print(f"{key}={str(required).lower()}")
    print(f"reason={reason}")
    print(f"changed_paths={len(paths)}")


if __name__ == "__main__":
    main()
