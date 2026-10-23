"""Install this account's staging startup/monitor jobs on the dedicated Mac.

Run after copying start-after-login.sh and monitor.py into the private directory.
Does not change system daemons, FileVault, Docker settings or other login jobs.
"""
import os
import pathlib
import plistlib
import subprocess

root = pathlib.Path.home() / "dieselbridge-staging/private"
directory = pathlib.Path.home() / "Library/LaunchAgents"
assert root.is_dir()
directory.mkdir(exist_ok=True)
jobs = {
    "start": {
        "ProgramArguments": ["/bin/sh", str(root / "start-after-login.sh")],
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 60,
    },
    "monitor": {
        "ProgramArguments": ["/opt/homebrew/bin/python3", str(root / "monitor.py")],
        "StartInterval": 60,
    },
}
for suffix, extra in jobs.items():
    label = f"com.dieselbridge.staging.{suffix}"
    path = directory / f"{label}.plist"
    config = {
        "Label": label, "RunAtLoad": True, **extra,
        "StandardOutPath": str(root / f"{suffix}.log"),
        "StandardErrorPath": str(root / f"{suffix}-error.log"),
    }
    target = f"gui/{os.getuid()}/{label}"
    if path.exists():
        existing = plistlib.loads(path.read_bytes())
        if existing.get("Label") != label or existing.get("ProgramArguments") != config["ProgramArguments"]:
            raise RuntimeError("Conflicting login job; refusing replacement")
        if existing == config:
            active = subprocess.run(["launchctl", "print", target], capture_output=True)
            if active.returncode != 0:
                subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)], check=True)
            print(label, "already configured")
            continue
        active = subprocess.run(["launchctl", "print", target], capture_output=True)
        if active.returncode == 0:
            subprocess.run(["launchctl", "bootout", target], check=True)
    path.write_bytes(plistlib.dumps(config))
    path.chmod(0o600)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)], check=True)
    print(label, "installed")
