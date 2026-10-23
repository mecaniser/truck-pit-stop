#!/usr/bin/env python3
"""Private forward-auth gate for the two synthetic Mac test applications.

Caddy must overwrite X-Test-Host, X-Test-Method, X-Test-Uri and
X-Test-Client-IP on every request to this process. Never expose port 18680.
No application Authorization header is read, returned, or replaced here.
"""
import base64
from collections import OrderedDict, deque
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import threading
import time
from urllib.parse import parse_qs, unquote, urlsplit

HOSTS = frozenset(("dieselbridge-test.elisprotech.com", "tph-test.elisprotech.com"))
CONFIG = Path.home() / "mac-hosting/test-public/private/access.json"
ACCESS = "__Host-test-access"
CSRF = "__Host-test-csrf"
ACCESS_TTL = 8 * 60 * 60
CSRF_TTL = 10 * 60
MAX_BODY = 2048
SCRYPT = dict(n=16384, r=8, p=1, dklen=64)


def load_config(path=CONFIG):
    """Require the fixed private location, no symlinks, and owner-only files."""
    path = Path(path).absolute()
    if path != CONFIG.absolute():
        raise ValueError("configuration must use the fixed private path")
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("configuration symlink refused")
    private = path.parent.stat()
    if stat.S_IMODE(private.st_mode) != 0o700 or private.st_uid != os.getuid():
        raise ValueError("private directory must be owned by this user and mode 0700")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > 4096):
            raise ValueError("configuration must be an owned private regular file")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as source:
            config = json.load(source)
    finally:
        os.close(fd)
    expected = {"cookie_key", "password_salt", "password_hash"}
    if not isinstance(config, dict) or set(config) != expected:
        raise ValueError("invalid configuration fields")
    for field, length in (("cookie_key", 64), ("password_salt", 32), ("password_hash", 128)):
        if not isinstance(config[field], str) or not re.fullmatch(r"[0-9a-f]{%d}" % length, config[field]):
            raise ValueError("invalid credential encoding")
    return {key: bytes.fromhex(value) for key, value in config.items()}


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class Gate:
    def __init__(self, config, now=time.time):
        self.config = config
        self.now = now
        self.lock = threading.Lock()
        self.scrypt_slots = threading.BoundedSemaphore(2)
        self.limits = OrderedDict()

    def token(self, host, purpose):
        ttl = ACCESS_TTL if purpose == "access" else CSRF_TTL
        issued = int(self.now())
        payload = b64(json.dumps({"host": host, "purpose": purpose, "iat": issued,
                                 "exp": issued + ttl, "nonce": secrets.token_hex(16)},
                                separators=(",", ":"), sort_keys=True).encode())
        signature = b64(hmac.digest(self.config["cookie_key"], payload.encode(), "sha256"))
        return payload + "." + signature

    def valid(self, token, host, purpose):
        if host not in HOSTS or not isinstance(token, str) or len(token) > 1024:
            return False
        try:
            payload, signature = token.split(".")
            if not re.fullmatch(r"[A-Za-z0-9_-]+", payload + signature):
                return False
            expected = b64(hmac.digest(self.config["cookie_key"], payload.encode(), "sha256"))
            if not hmac.compare_digest(signature, expected):
                return False
            data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            ttl = ACCESS_TTL if purpose == "access" else CSRF_TTL
            now = self.now()
            return (set(data) == {"host", "purpose", "iat", "exp", "nonce"}
                    and data["host"] == host and data["purpose"] == purpose
                    and type(data["iat"]) is int and type(data["exp"]) is int
                    and data["iat"] <= now < data["exp"]
                    and data["exp"] - data["iat"] == ttl
                    and isinstance(data["nonce"], str)
                    and re.fullmatch(r"[0-9a-f]{32}", data["nonce"]) is not None)
        except (ValueError, TypeError, KeyError, UnicodeError):
            return False

    def allow(self, ip, login=False):
        """Sliding-window bounds; a full IP table refuses new peers, never evicts."""
        now = self.now()
        kind = "login" if login else "request"
        max_global, max_peer = (30, 5) if login else (6000, 1200)
        with self.lock:
            for key in list(self.limits):
                events = self.limits[key]
                while events and events[0] <= now - 60:
                    events.popleft()
                if not events:
                    del self.limits[key]
            global_key, peer_key = (kind, "*"), (kind, ip)
            if peer_key not in self.limits and len(self.limits) >= 4096:
                return False
            global_events = self.limits.setdefault(global_key, deque())
            peer_events = self.limits.setdefault(peer_key, deque())
            if len(global_events) >= max_global or len(peer_events) >= max_peer:
                return False
            global_events.append(now)
            peer_events.append(now)
            return True

    def password_matches(self, password):
        if not 32 <= len(password) <= 256 or not self.scrypt_slots.acquire(blocking=False):
            return False
        try:
            digest = hashlib.scrypt(password.encode("utf-8"), salt=self.config["password_salt"], **SCRYPT)
            return hmac.compare_digest(digest, self.config["password_hash"])
        finally:
            self.scrypt_slots.release()


def cookie(name, value, ttl):
    return f"{name}={value}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age={ttl}"


class Handler(BaseHTTPRequestHandler):
    server_version = "TestAccess"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_args):
        pass

    def log_error(self, *_args):
        pass

    def reply(self, status, body=b"", headers=()):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def single(self, key):
        values = self.headers.get_all(key, [])
        if len(values) != 1:
            raise ValueError("missing or repeated header")
        return values[0]

    def context(self):
        host = self.single("X-Test-Host")
        method = self.single("X-Test-Method")
        uri = self.single("X-Test-Uri")
        ip = str(ipaddress.ip_address(self.single("X-Test-Client-IP")))
        if (host not in HOSTS or self.single("Host") != host
                or method not in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
                or len(uri) > 8192 or not uri.startswith("/") or uri.startswith("//")
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in uri)):
            raise ValueError("invalid proxy context")
        # Caddy forward_auth replaces the path but preserves the original query.
        # Only the private verification endpoint accepts this inherited query;
        # the original method/URI remain in the overwritten proxy headers.
        if urlsplit(self.path).path != "/verify" and (method != self.command or uri != self.path):
            raise ValueError("incorrect original request")
        if not self.server.gate.allow(ip):
            self.reply(429, b"Too many requests", (("Retry-After", "60"),))
            return None
        return host, method, uri, ip

    def read_cookies(self):
        raw = self.headers.get_all("Cookie", [])
        if len(raw) > 1 or (raw and len(raw[0]) > 8192):
            raise ValueError("invalid cookie header")
        # Duplicate security cookie names are ambiguous: reject them.
        if raw:
            for name in (ACCESS, CSRF):
                if len(re.findall(r"(?:^|;)\s*" + re.escape(name) + r"=", raw[0])) > 1:
                    raise ValueError("duplicate gate cookie")
        jar = cookies.SimpleCookie()
        if raw:
            jar.load(raw[0])
        return {key: value.value for key, value in jar.items()}

    def form(self, host, authenticated):
        token = self.server.gate.token(host, "csrf")
        action = "/_test-access/logout" if authenticated else "/_test-access"
        password = "" if authenticated else '<label>Test password <input type="password" name="password" autocomplete="current-password" required maxlength="256"></label>'
        button = "Lock test site" if authenticated else "Open test site"
        body = (f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>Private test site</title><h1>Private test site</h1><p>Synthetic data. Test access only.</p>'
                f'<form method="post" action="{action}"><input type="hidden" name="csrf" value="{token}">{password}<button>{button}</button></form></html>').encode()
        self.reply(200, body, (("Set-Cookie", cookie(CSRF, token, CSRF_TTL)),))

    def post_form(self, host, jar):
        if self.single("Origin") != "https://" + host:
            raise ValueError("origin mismatch")
        if self.headers.get_all("Transfer-Encoding"):
            raise ValueError("transfer encoding refused")
        length_text = self.single("Content-Length")
        if not re.fullmatch(r"[0-9]{1,4}", length_text):
            raise ValueError("invalid length")
        length = int(length_text)
        if length > MAX_BODY or length == 0:
            raise ValueError("invalid form size")
        if self.single("Content-Type").lower() != "application/x-www-form-urlencoded":
            raise ValueError("invalid content type")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("incomplete form")
        form = parse_qs(raw.decode("utf-8"), strict_parsing=True, max_num_fields=3, keep_blank_values=True)
        expected = {"csrf", "password"} if self.path == "/_test-access" else {"csrf"}
        if set(form) != expected or any(len(value) != 1 for value in form.values()):
            raise ValueError("invalid form fields")
        token = form["csrf"][0]
        saved = jar.get(CSRF, "")
        if not hmac.compare_digest(token.encode(), saved.encode()) or not self.server.gate.valid(token, host, "csrf"):
            raise ValueError("invalid csrf")
        return {key: value[0] for key, value in form.items()}

    def dispatch(self):
        context = self.context()
        if context is None:
            return
        host, method, uri, ip = context
        jar = self.read_cookies()
        authenticated = self.server.gate.valid(jar.get(ACCESS, ""), host, "access")
        if urlsplit(self.path).path == "/verify" and self.command == "GET":
            if authenticated:
                self.reply(204)
            else:
                accept = self.headers.get("Accept", "").lower()
                path = unquote(urlsplit(uri).path).replace("\\", "/").lower()
                # Auth redirects are browser navigations only; API clients get an explicit denial.
                api = any(part == "api" for part in path.split("/"))
                if method == "GET" and "text/html" in accept and not api:
                    self.reply(303, headers=(("Location", "/_test-access"),))
                else:
                    self.reply(403, b"Test access required")
            return
        if self.path == "/_test-access" and self.command == "GET":
            self.form(host, authenticated)
            return
        if self.path in ("/_test-access", "/_test-access/logout") and self.command == "POST":
            if not self.server.gate.allow(ip, login=True):
                self.reply(429, b"Too many attempts", (("Retry-After", "60"),))
                return
            form = self.post_form(host, jar)
            if self.path == "/_test-access/logout":
                self.reply(303, headers=(("Location", "/_test-access"),
                                         ("Set-Cookie", cookie(ACCESS, "", 0)),
                                         ("Set-Cookie", cookie(CSRF, "", 0))))
                return
            if not self.server.gate.password_matches(form["password"]):
                self.reply(403, b"Access denied")
                return
            token = self.server.gate.token(host, "access")
            self.reply(303, headers=(("Location", "/"),
                                     ("Set-Cookie", cookie(ACCESS, token, ACCESS_TTL)),
                                     ("Set-Cookie", cookie(CSRF, "", 0))))
            return
        self.reply(404, b"Not found")

    def handle_request(self):
        try:
            self.dispatch()
        except (ValueError, UnicodeError, cookies.CookieError):
            self.reply(403, b"Access denied")
        except (socket.timeout, TimeoutError):
            self.close_connection = True
        except Exception:
            # Avoid exceptions containing request content in stderr or error responses.
            try:
                self.reply(503, b"Access unavailable")
            except Exception:
                self.close_connection = True

    do_GET = handle_request
    do_HEAD = handle_request
    do_POST = handle_request
    do_PUT = handle_request
    do_PATCH = handle_request
    do_DELETE = handle_request
    do_OPTIONS = handle_request


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, address, gate):
        if address[0] != "127.0.0.1":
            raise ValueError("loopback binding required")
        self.gate = gate
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass


def main():
    # No arbitrary command-line config path or public bind option.
    try:
        gate = Gate(load_config())
        with Server(("127.0.0.1", 18680), gate) as server:
            server.serve_forever()
    except Exception:
        raise SystemExit("Test access gate unavailable; inspect private configuration permissions") from None


if __name__ == "__main__":
    main()
