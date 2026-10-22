"""Focused hostile-request and native bearer preservation checks for the gate."""
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import re
import secrets
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

spec = importlib.util.spec_from_file_location("access_gate", Path(__file__).with_name("access_gate.py"))
gate_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate_module)
H1, H2 = sorted(gate_module.HOSTS)


class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(32)
        salt = secrets.token_bytes(16)
        cls.config = {"cookie_key": secrets.token_bytes(32), "password_salt": salt,
                      "password_hash": hashlib.scrypt(cls.password.encode(), salt=salt, **gate_module.SCRYPT)}

    def setUp(self):
        self.clock = [1700000000]
        self.gate = gate_module.Gate(self.config, now=lambda: self.clock[0])
        self.server = gate_module.Server(("127.0.0.1", 0), self.gate)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path="/verify", method="GET", host=H1, original_uri="/", original_method="GET", extra=None, body=None):
        headers = {"Host": host, "X-Test-Host": host, "X-Test-Method": original_method,
                   "X-Test-Uri": original_uri if path == "/verify" else path,
                   "X-Test-Client-IP": "192.0.2.1", "Accept": "text/html"}
        headers.update(extra or {})
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        result = response.status, response.getheaders(), response.read()
        connection.close()
        return result

    def csrf_form(self, host=H1):
        status, headers, body = self.request("/_test-access", host=host)
        self.assertEqual(status, 200)
        token = re.search(rb'name="csrf" value="([^"]+)"', body).group(1).decode()
        return token, f"{gate_module.CSRF}={token}"

    def login(self, host=H1, password=None, origin=None, csrf_host=None, fields=None):
        token, saved_cookie = self.csrf_form(csrf_host or host)
        data = {"csrf": token, "password": self.password if password is None else password}
        data.update(fields or {})
        return self.request("/_test-access", "POST", host=host, original_method="POST",
                            extra={"Cookie": saved_cookie, "Origin": origin or "https://" + host,
                                   "Content-Type": "application/x-www-form-urlencoded"}, body=urlencode(data))

    def test_valid_host_bound_expiring_cookie(self):
        token = self.gate.token(H1, "access")
        self.assertTrue(self.gate.valid(token, H1, "access"))
        self.assertFalse(self.gate.valid(token, H2, "access"))
        self.assertFalse(self.gate.valid(token, H1, "csrf"))
        self.clock[0] += gate_module.ACCESS_TTL
        self.assertFalse(self.gate.valid(token, H1, "access"))

    def test_forgery_future_cookie_and_malformed_tokens_denied(self):
        token = self.gate.token(H1, "access")
        payload, signature = token.split(".")
        self.assertFalse(self.gate.valid(payload + "." + ("A" if signature[0] != "A" else "B") + signature[1:], H1, "access"))
        self.clock[0] -= 1
        self.assertFalse(self.gate.valid(token, H1, "access"))
        for malformed in ("", "x.y.z", "a.%%%", "\u2603", "x" * 1025):
            self.assertFalse(self.gate.valid(malformed, H1, "access"))

    def test_browser_redirect_is_fixed_and_apis_unsafe_requests_denied(self):
        status, headers, _ = self.request(original_uri="/?next=https://attacker.invalid")
        self.assertEqual(status, 303)
        self.assertEqual(dict(headers)["Location"], "/_test-access")
        for path in ("/api", "/api/users", "/%61pi/private", "/API/private"):
            self.assertEqual(self.request(original_uri=path)[0], 403)
        for method in ("POST", "PUT", "DELETE", "HEAD", "OPTIONS"):
            self.assertEqual(self.request(original_method=method)[0], 403)
        self.assertEqual(self.request(extra={"Accept": "application/json"})[0], 403)

    def test_successful_login_cookie_flags_and_fixed_destination(self):
        status, headers, _ = self.login()
        self.assertEqual(status, 303)
        self.assertEqual(dict(headers)["Location"], "/")
        values = [value for key, value in headers if key == "Set-Cookie"]
        session_cookie = next(value for value in values if value.startswith(gate_module.ACCESS + "="))
        for flag in ("Path=/", "Secure", "HttpOnly", "SameSite=Strict", "Max-Age=28800"):
            self.assertIn(flag, session_cookie)
        self.assertNotIn("Domain", session_cookie)
        token = session_cookie.split(";", 1)[0].split("=", 1)[1]
        self.assertEqual(self.request(extra={"Cookie": f"{gate_module.ACCESS}={token}"})[0], 204)
        self.assertEqual(self.request(host=H2, extra={"Cookie": f"{gate_module.ACCESS}={token}"})[0], 303)

    def test_wrong_password_origin_and_cross_host_csrf_denied(self):
        self.assertEqual(self.login(password=secrets.token_urlsafe(32))[0], 403)
        self.assertEqual(self.login(origin="https://attacker.invalid")[0], 403)
        self.assertEqual(self.login(csrf_host=H2)[0], 403)
        self.assertEqual(self.login(fields={"next": "https://attacker.invalid"})[0], 403)

    def test_missing_expired_and_mismatched_csrf_denied(self):
        token, saved_cookie = self.csrf_form()
        self.clock[0] += gate_module.CSRF_TTL
        extras = {"Cookie": saved_cookie, "Origin": "https://" + H1,
                  "Content-Type": "application/x-www-form-urlencoded"}
        body = urlencode({"csrf": token, "password": self.password})
        self.assertEqual(self.request("/_test-access", "POST", original_method="POST", extra=extras, body=body)[0], 403)
        self.clock[0] -= gate_module.CSRF_TTL
        extras["Cookie"] = ""
        self.assertEqual(self.request("/_test-access", "POST", original_method="POST", extra=extras, body=body)[0], 403)
        extras["Cookie"] = saved_cookie
        body = urlencode({"csrf": self.gate.token(H1, "csrf"), "password": self.password})
        self.assertEqual(self.request("/_test-access", "POST", original_method="POST", extra=extras, body=body)[0], 403)

    def test_logout_requires_post_origin_and_csrf_and_clears_cookies(self):
        self.assertEqual(self.request("/_test-access/logout")[0], 404)
        token, saved_cookie = self.csrf_form()
        body = urlencode({"csrf": token})
        status, headers, _ = self.request("/_test-access/logout", "POST", original_method="POST",
                                        extra={"Cookie": saved_cookie, "Origin": "https://" + H1,
                                               "Content-Type": "application/x-www-form-urlencoded"}, body=body)
        self.assertEqual(status, 303)
        values = [value for key, value in headers if key == "Set-Cookie"]
        self.assertEqual(len(values), 2)
        self.assertTrue(all("Max-Age=0" in value for value in values))

    def test_authorization_bearer_is_not_consumed_or_replaced(self):
        token = self.gate.token(H1, "access")
        bearer = "Bearer " + secrets.token_urlsafe(24)
        status, headers, body = self.request(original_uri="/api/customer", original_method="POST",
                                             extra={"Cookie": f"{gate_module.ACCESS}={token}", "Authorization": bearer})
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")
        self.assertNotIn("authorization", {key.lower() for key, _ in headers})
        self.assertEqual(self.request(extra={"Authorization": bearer})[0], 303)

    def test_invalid_proxy_context_and_duplicate_cookie_denied(self):
        for extra in ({"Host": H2}, {"X-Test-Host": "attacker.invalid"}, {"X-Test-Method": "BOGUS"},
                      {"X-Test-Uri": "//attacker.invalid"}, {"X-Test-Client-IP": "192.0.2.1, 192.0.2.2"}):
            self.assertEqual(self.request(extra=extra)[0], 403)
        token = self.gate.token(H1, "access")
        self.assertEqual(self.request(extra={"Cookie": f"{gate_module.ACCESS}={token}; {gate_module.ACCESS}={token}"})[0], 403)
        self.assertEqual(self.request("/verify?x=1")[0], 404)

    def test_body_bound_and_duplicate_fields_denied(self):
        token, saved_cookie = self.csrf_form()
        extras = {"Cookie": saved_cookie, "Origin": "https://" + H1,
                  "Content-Type": "application/x-www-form-urlencoded"}
        self.assertEqual(self.request("/_test-access", "POST", original_method="POST", extra=extras,
                                     body="x=" + "x" * 2048)[0], 403)
        body = urlencode({"csrf": token, "password": self.password}) + "&password=other"
        self.assertEqual(self.request("/_test-access", "POST", original_method="POST", extra=extras, body=body)[0], 403)

    def test_per_peer_and_global_rate_limits_expire(self):
        for _ in range(5):
            self.assertTrue(self.gate.allow("192.0.2.1", login=True))
        self.assertFalse(self.gate.allow("192.0.2.1", login=True))
        for index in range(25):
            self.assertTrue(self.gate.allow(f"198.51.100.{index}", login=True))
        self.assertFalse(self.gate.allow("203.0.113.1", login=True))
        self.clock[0] += 60
        self.assertTrue(self.gate.allow("192.0.2.1", login=True))

    def test_wrong_password_http_rate_limit_and_fail_closed_exception(self):
        for _ in range(5):
            self.assertEqual(self.login(password="x" * 32)[0], 403)
        self.assertEqual(self.login(password="x" * 32)[0], 429)
        self.gate.valid = lambda *_args: (_ for _ in ()).throw(RuntimeError("private detail"))
        status, _, body = self.request()
        self.assertEqual(status, 503)
        self.assertNotIn(b"private detail", body)

    def test_server_refuses_public_bind(self):
        with self.assertRaises(ValueError):
            gate_module.Server(("0.0.0.0", 0), self.gate)


class ConfigTests(unittest.TestCase):
    def test_private_path_permissions_and_symlink_refusal(self):
        config = {"cookie_key": secrets.token_hex(32), "password_salt": secrets.token_hex(16),
                  "password_hash": secrets.token_hex(64)}
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory).resolve() / "private"
            private.mkdir(mode=0o700)
            path = private / "access.json"
            path.write_text(json.dumps(config))
            path.chmod(0o600)
            with patch.object(gate_module, "CONFIG", path):
                self.assertEqual(gate_module.load_config(path)["cookie_key"], bytes.fromhex(config["cookie_key"]))
                path.chmod(0o644)
                with self.assertRaises(ValueError):
                    gate_module.load_config(path)
                path.chmod(0o600)
                target = private / "real.json"
                path.rename(target)
                path.symlink_to(target)
                with self.assertRaises(ValueError):
                    gate_module.load_config(path)


if __name__ == "__main__":
    unittest.main()
