"""Execute the existing critical backend files or their full-suite complement."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
COLLECT_FILES = '''
import json,sys
from pathlib import Path
import pytest
class Files:
    def pytest_collection_finish(self, session):
        print("CI_FILES=" + json.dumps(sorted({str(item.path.relative_to(Path.cwd())) for item in session.items})))
sys.exit(pytest.main(["--collect-only", "-q", *sys.argv[1:]], plugins=[Files()]))
'''


def critical_files(root: Path, patterns: list[str]) -> list[str]:
    if not patterns or len(patterns) != len(set(patterns)):
        raise ValueError("Critical patterns must be nonempty and unique")
    files = set()
    for pattern in patterns:
        if not pattern.startswith("tests/") or ".." in pattern.split("/") or "\\" in pattern:
            raise ValueError("Unsafe critical test pattern")
        matches = sorted(p for p in root.glob(pattern) if p.is_file() and p.suffix == ".py")
        if not matches:
            raise ValueError(f"Critical test pattern matched no files: {pattern}")
        resolved = {str(p.relative_to(root)) for p in matches}
        if files & resolved:
            raise ValueError("Critical patterns overlap")
        files.update(resolved)
    return sorted(files)


def verify_partition(root: Path, files: list[str]):
    def collect(arguments):
        output = subprocess.check_output([sys.executable, "-c", COLLECT_FILES, *arguments], cwd=root, text=True)
        return set(json.loads(next(line.removeprefix("CI_FILES=") for line in output.splitlines() if line.startswith("CI_FILES="))))
    all_files = collect([])
    critical = collect(files)
    remaining = collect([arg for file in files for arg in ("--ignore", file)])
    if not all_files or not critical or not remaining or critical & remaining or critical | remaining != all_files:
        raise ValueError("Collected backend test partitions must be disjoint and cover the full suite")
    print(f"Backend partition coverage: {len(critical)} critical + {len(remaining)} remaining = {len(all_files)} files, no overlap")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("critical", "remaining", "verify"))
    parser.add_argument("--list", action="store_true", help="Print arguments without running tests")
    args = parser.parse_args()
    root = REPO / "backend"
    patterns = json.loads((REPO / ".github/critical-tests.json").read_text())["backend"]
    files = critical_files(root, patterns)
    if args.mode == "verify":
        verify_partition(root, files)
        return
    test_args = files if args.mode == "critical" else [arg for file in files for arg in ("--ignore", file)]
    if args.list:
        print(json.dumps(test_args))
        return
    subprocess.run([sys.executable, "-m", "pytest", *test_args], cwd=root, check=True)


if __name__ == "__main__":
    main()
