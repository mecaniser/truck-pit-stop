"""Read-only HTTP acceptance against the loopback staging gateway.

Accepts the private seed password JSON on stdin; never prints credentials/tokens.
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:18080"


def request(path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        BASE + path, data=json.dumps(data).encode() if data else None, headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None


def main():
    passwords = json.load(sys.stdin)
    status, body = request("/health/ready")
    assert status == 200 and body["environment"] == "staging"
    print("readiness PASS")
    tokens, customers = {}, {}
    for name in ("alpha", "beta"):
        status, body = request("/api/v1/auth/login", {
            "email": f"staging-{name}@example.com", "password": passwords[name],
        })
        assert status == 200, ("login", name, status)
        tokens[name] = body["access_token"]
        status, body = request("/api/v1/customers", token=tokens[name])
        assert status == 200 and len(body) == 1, ("customers", name, status)
        customers[name] = body[0]["id"]
        print(name, "login and own customer PASS")
    for name, other in (("alpha", "beta"), ("beta", "alpha")):
        status, _ = request("/api/v1/customers/" + customers[other], token=tokens[name])
        assert status in (403, 404), ("tenant isolation", status)
        print(name, "cross-tenant denied", status)
    assert request("/api/v1/customers")[0] in (401, 403)
    print("unauthenticated denied PASS")


if __name__ == "__main__":
    main()
