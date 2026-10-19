"""Print a read-only, exact-SHA CI and production release receipt for one PR."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


PROJECT_ID = "78a30cb6-c422-458a-ad8f-daa02073b579"
PRODUCTION_ID = "b5c9fdf5-4430-4cb3-97b9-cd739d7d5ece"
WEB_SERVICE_ID = "57db24db-bb57-4464-8263-5d2064f9221e"
API_ORIGIN = "https://api.dieselbridge.com"
CHECK_NAMES = (
    "Migration graph", "Backend tests", "Backend full suite (informational)",
    "Frontend checks", "Frontend full suite (informational)", "Playwright smoke",
)


def command_json(*args: str) -> dict | list:
    attempts = 2 if args[0] == "gh" else 1
    for index in range(attempts):
        try:
            result = subprocess.run(args, capture_output=True, text=True, check=True, timeout=30)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError:
            if index + 1 == attempts:
                raise
    raise AssertionError("unreachable")


def attempt(label: str, operation):
    try:
        return operation(), None
    except (OSError, ValueError, KeyError, StopIteration, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, HTTPError, URLError) as error:
        return None, f"{label} unavailable ({type(error).__name__})"


def http_json(path: str) -> dict:
    with urlopen(f"{API_ORIGIN}{path}", timeout=5) as response:
        return json.load(response)


def latest_run(sha: str, event: str) -> dict | None:
    runs = command_json(
        "gh", "run", "list", "--commit", sha, "--event", event,
        "--workflow", "quality.yml", "--limit", "20", "--json",
        "databaseId,headSha,event,status,conclusion,createdAt,url",
    )
    return next((run for run in runs if run["headSha"] == sha and run["event"] == event), None)


def report_run(lines: list[str], label: str, sha: str, event: str) -> None:
    run, error = attempt(label, lambda: latest_run(sha, event))
    if error or not run:
        lines.append(f"- {label}: unknown ({error or 'no run for exact SHA'})")
        return
    lines.append(f"- {label}: {run['status']}/{run['conclusion'] or 'pending'} — {run['url']}")
    detail, detail_error = attempt("job detail", lambda: command_json(
        "gh", "run", "view", str(run["databaseId"]), "--json", "jobs"))
    if detail_error:
        lines.append(f"  - Jobs: unknown ({detail_error})")
        return
    jobs = {job["name"]: job for job in detail["jobs"]}
    for name in CHECK_NAMES:
        job = jobs.get(name)
        if not job:
            lines.append(f"  - {name}: pending/not scheduled")
            continue
        omitted = any(step["name"].startswith("Frontend-only PR;") and step.get("conclusion") == "success"
                      for step in job.get("steps", []))
        suffix = " (backend pytest omitted by scope)" if omitted else ""
        failed = [step["name"] for step in job.get("steps", []) if step.get("conclusion") == "failure"]
        if failed:
            suffix += f" (failed step: {', '.join(failed)})"
        lines.append(f"  - {name}: {job['conclusion'] or 'pending'}{suffix}")


def production_deployment() -> dict | None:
    status = command_json(
        "railway", "status", "--project", PROJECT_ID, "--environment", PRODUCTION_ID, "--json")
    environments = [edge["node"] for edge in status["environments"]["edges"]]
    environment = next(item for item in environments if item["id"] == PRODUCTION_ID)
    instances = [edge["node"] for edge in environment["serviceInstances"]["edges"]]
    instance = next(item for item in instances if item["serviceId"] == WEB_SERVICE_ID)
    return instance.get("latestDeployment")


def receipt(pr_number: int) -> str:
    pr = command_json(
        "gh", "pr", "view", str(pr_number), "--json",
        "number,title,url,headRefOid,mergeCommit,mergedAt,isDraft")
    head = pr["headRefOid"]
    merge = (pr.get("mergeCommit") or {}).get("oid") if pr.get("mergedAt") else None
    lines = [
        f"# Release receipt — PR #{pr_number}", "",
        f"Observed: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"PR: {pr['url']}", f"Head SHA: `{head}`",
        f"Merge SHA: `{merge}`" if merge else "Merge SHA: unknown (PR not merged)",
        "", "## CI", "",
    ]
    report_run(lines, "PR checks", head, "pull_request")
    if merge:
        report_run(lines, "Main checks", merge, "push")
    lines.extend(["", "## Production web", ""])
    deployment, deployment_error = attempt("Railway deployment", production_deployment)
    if deployment_error or not deployment:
        lines.append(f"- Railway deployment: unknown ({deployment_error or 'no deployment'})")
    else:
        metadata = deployment.get("meta") or {}
        deployed_sha = metadata.get("commitHash")
        lines.extend([
            f"- Railway deployment: `{deployment.get('id') or 'unknown'}` / {deployment.get('status') or 'unknown'}",
            f"- Railway source SHA: `{deployed_sha or 'unknown'}`",
        ])
        if merge:
            lines.append(f"- Merge SHA matches Railway source: {'yes' if deployed_sha == merge else 'no/unknown'}")
    version, version_error = attempt("build-version", lambda: http_json("/build-version"))
    health, health_error = attempt("health", lambda: http_json("/health"))
    served_sha = version.get("sha") if version else None
    lines.append(f"- Served build SHA: `{served_sha}`" if served_sha else
                 f"- Served build SHA: unknown ({version_error or 'missing sha'})")
    lines.append(f"- Health: {health.get('status', 'unknown')}" if health else
                 f"- Health: unknown ({health_error})")
    if merge:
        lines.append(f"- Merge SHA matches served build: {'yes' if served_sha == merge else 'no' if served_sha else 'unknown'}")
    lines.extend(["", "Browser acceptance: not measured by this command.",
                  "A successful CI run, Railway status, and HTTP response are distinct evidence."])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr", type=int, help="GitHub PR number")
    args = parser.parse_args()
    print(receipt(args.pr), end="")


if __name__ == "__main__":
    main()
