"""One bounded read-only staging sample; launchd invokes once per minute.

No credentials, production access, repairs, worker triggers or log bodies.
Observation starts immediately; the accepted 24-hour window is set separately
only after reboot and five-worker acceptance pass.
"""
import datetime
import json
import pathlib
import shutil
import subprocess
import urllib.request

ROOT = pathlib.Path.home() / "dieselbridge-staging/private"
DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"
NAMES = ["dieselbridge-staging-" + x + "-1" for x in ("web", "postgres", "redis", "gateway")]
EXPECTED_SOURCE = "626194996e78bd42556ce476847473e5730aa388"


def sample():
    result = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "ok": False}
    try:
        with urllib.request.urlopen("http://127.0.0.1:18080/health/ready", timeout=5) as response:
            health = json.load(response)
        with urllib.request.urlopen("http://127.0.0.1:18080/build-version", timeout=5) as response:
            build = json.load(response)
        raw = subprocess.run(
            [DOCKER, "inspect", "--format", '{{json .State}}', *NAMES],
            capture_output=True, text=True, timeout=15, check=True,
        )
        states = [json.loads(line) for line in raw.stdout.splitlines()]
        result.update(
            ready=health.get("status"), environment=health.get("environment"),
            source=build.get("sha"),
            containers={name: {"status": state.get("Status"),
                               "health": state.get("Health", {}).get("Status"),
                               "started": state.get("StartedAt"),
                               "oom": state.get("OOMKilled")}
                        for name, state in zip(NAMES, states)},
            free_bytes=shutil.disk_usage(ROOT).free,
        )
        result["ok"] = (
            health.get("status") == "ready" and health.get("environment") == "staging"
            and build.get("sha") == EXPECTED_SOURCE
            and len(states) == 4 and all(state.get("Running") and not state.get("OOMKilled") for state in states)
            and all(state.get("Health", {}).get("Status") == "healthy" for state in states[:3])
            and result["free_bytes"] > 20 * 1024 ** 3
        )
    except Exception as error:
        result["error_type"] = type(error).__name__
    path = ROOT / "monitor.jsonl"
    if path.exists() and path.stat().st_size > 10 * 1024 ** 2:
        path.replace(ROOT / "monitor.previous.jsonl")
    with path.open("a") as output:
        output.write(json.dumps(result, sort_keys=True) + "\n")
    path.chmod(0o600)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    sample()
