import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_api_deployment_waits_for_health_before_cutover():
    config = json.loads((REPOSITORY_ROOT / "railway.json").read_text())

    assert config["deploy"]["healthcheckPath"] == "/health"
    assert config["deploy"]["healthcheckTimeout"] == 300
