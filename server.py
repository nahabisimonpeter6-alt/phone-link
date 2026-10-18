#!/usr/bin/env python3
"""PhoneLink: a dependency-free location relay and private web dashboard."""
import argparse
import hashlib
import hmac
import ipaddress
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
MAX_BODY = 8192
SESSION_SECONDS = 7 * 24 * 3600
PAIR_SECONDS = 600
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


class AppState:
    """Database and access controls shared by local HTTP and hosted WSGI servers."""

    def __init__(self, db_path, public_url=None):
        self.db_path = str(db_path)
        self.public_url = public_url.rstrip("/") if public_url else None
        if self.public_url:
            parsed = urlsplit(self.public_url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path:
                raise ValueError("--public-url must be an origin such as https://phone.example.com")
        self.rate_lock = threading.Lock()
        self.rates = defaultdict(deque)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                -- Rollback journaling also supports a small, single-worker
                -- hosted app without WAL's shared-memory requirement.
                PRAGMA journal_mode=DELETE;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    salt TEXT NOT NULL, password TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    name TEXT NOT NULL, token_hash TEXT UNIQUE,
                    pairing_hash TEXT UNIQUE, pairing_expires REAL,
                    paired_at REAL, seen_at REAL, tracking INTEGER DEFAULT 0,
                    latitude REAL, longitude REAL, accuracy REAL, located_at REAL,
                    battery INTEGER, created_at REAL NOT NULL
                );
            """)
        os.chmod(db_path, 0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def rate_limit(self, key, limit, seconds=60):
        now = time.time()
        with self.rate_lock:
            if len(self.rates) > 4096:
                for old_key in list(self.rates):
                    if not self.rates[old_key] or self.rates[old_key][-1] < now - 3600:
                        del self.rates[old_key]
            items = self.rates[key]
            while items and items[0] < now - seconds:
                items.popleft()
            if len(items) >= limit:
                raise APIError(429, "Too many attempts. Please wait a minute and try again.")
            items.append(now)


class PhoneServer(AppState, ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, db_path, public_url=None):
        AppState.__init__(self, db_path, public_url)
        ThreadingHTTPServer.__init__(self, address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "PhoneLink/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, fmt, *args):
        # Never log request bodies, passwords, pairing codes, or device tokens.
        super().log_message(fmt, *args)

    def origin(self):
        if self.server.public_url:
            return self.server.public_url
        host = self.headers.get("Host", "")
        if not re.fullmatch(r"[a-zA-Z0-9.\[\]:-]+", host):
            raise APIError(400, "Invalid host.")
        parsed = urlsplit("http://" + host)
        name = parsed.hostname
        # Without an explicit public URL only localhost / private LAN are allowed.
        allowed = name == "localhost"
        try:
            ip = ipaddress.ip_address(name or "")
            allowed = ip.is_private or ip.is_loopback
        except ValueError:
            pass
        if not allowed:
            raise APIError(400, "Set --public-url before using a public hostname.")
        return "http://" + host

    def respond(self, status, value, cookie=None):
        content = json.dumps(value, allow_nan=False).encode()
        self.send_response(status)
        self.secure_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if status == 429:
            self.send_header("Retry-After", "60")
        self.end_headers()
        self.wfile.write(content)

    def secure_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        # OSM's tile policy requires a Referer. Cross-origin requests receive
        # only this site's origin, never account names or location parameters.
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")

    def body(self):
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise APIError(415, "Send JSON data.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise APIError(400, "Invalid content length.")
        if length <= 0 or length > MAX_BODY:
            raise APIError(413, "Request body is missing or too large.")
        try:
            data = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            raise APIError(400, "Invalid JSON.")
        if not isinstance(data, dict):
            raise APIError(400, "Expected a JSON object.")
        return data

    def user(self, db):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except cookies.CookieError:
            raise APIError(401, "Please sign in.")
        token = jar.get("phonelink_session")
        row = db.execute("SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires>?",
                         (digest(token.value if token else ""), time.time())).fetchone()
        if not row:
            raise APIError(401, "Please sign in.")
        return row

    def session_cookie(self, token, expires=SESSION_SECONDS):
        secure = "; Secure" if self.origin().startswith("https:") else ""
        return f"phonelink_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={expires}{secure}"

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def dispatch(self, method):
        try:
            self.origin()
            path = urlsplit(self.path).path
            # Browser writes must originate from this dashboard. Native app requests
            # have no Origin and authenticate with a pairing code / bearer token.
            if method != "GET":
                origin = self.headers.get("Origin")
                if origin and origin != self.origin():
                    raise APIError(403, "Request origin does not match this server.")
                if self.headers.get("Sec-Fetch-Site") == "cross-site":
                    raise APIError(403, "Cross-site requests are not accepted.")
            if path.startswith("/api/"):
                with self.server.db() as db:
                    result, status, cookie = self.api(db, method, path)
                self.respond(status, result, cookie)
            elif method == "GET":
                self.static(path)
            else:
                raise APIError(404, "Not found.")
        except APIError as exc:
            self.respond(exc.status, {"error": exc.message})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            import traceback
            traceback.print_exc()
            self.respond(500, {"error": "Server error. Please try again."})

    def api(self, db, method, path):
        ip = self.client_address[0]
        now = time.time()
        data = self.body() if method == "POST" else {}
        if method == "GET" and path == "/api/health":
            db.execute("SELECT 1 FROM users LIMIT 1")
            return {"ok": True}, 200, None
        if method == "POST" and path in ("/api/register", "/api/login"):
            self.server.rate_limit((ip, "auth"), 12)
            username = data.get("username", "")
            password = data.get("password", "")
            if not isinstance(username, str) or not isinstance(password, str):
                raise APIError(400, "Enter a username and password.")
            username = username.strip().lower()
            if not re.fullmatch(r"[a-z0-9_.-]{3,40}", username):
                raise APIError(400, "Use 3–40 letters, numbers, dots, underscores or hyphens for your username.")
            if not 10 <= len(password) <= 128:
                raise APIError(400, "Use a password between 10 and 128 characters.")
            if path == "/api/register":
                uid, salt = secrets.token_hex(16), secrets.token_hex(16)
                try:
                    db.execute("INSERT INTO users VALUES(?,?,?,?)", (uid, username, salt, password_hash(password, salt)))
                except sqlite3.IntegrityError:
                    raise APIError(409, "This username is already in use.")
            else:
                user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
                salt = user["salt"] if user else "00" * 16
                calculated = password_hash(password, salt)
                if not user or not hmac.compare_digest(calculated, user["password"]):
                    raise APIError(401, "Incorrect username or password.")
                uid = user["id"]
            token = secrets.token_urlsafe(32)
            db.execute("DELETE FROM sessions WHERE expires<?", (now,))
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest(token), uid, now + SESSION_SECONDS))
            return {"username": username}, 200, self.session_cookie(token)
        if method == "POST" and path == "/api/pair":
            self.server.rate_limit((ip, "pair"), 10)
            code = data.get("code", "")
            if not isinstance(code, str):
                raise APIError(400, "Enter the pairing code from your dashboard.")
            code = code.replace("-", "").replace(" ", "").upper()
            row = db.execute("SELECT * FROM devices WHERE pairing_hash=? AND pairing_expires>? AND token_hash IS NULL", (digest(code), now)).fetchone()
            if not row:
                raise APIError(400, "Pairing code is invalid, expired, or already used. Create a new one on the dashboard.")
            token = secrets.token_urlsafe(32)
            # Atomic claim: two simultaneous requests cannot both pair one code.
            changed = db.execute("UPDATE devices SET token_hash=?, paired_at=?, pairing_hash=NULL, pairing_expires=NULL WHERE id=? AND token_hash IS NULL",
                                 (digest(token), now, row["id"])).rowcount
            if changed != 1:
                raise APIError(409, "This pairing code was already used.")
            return {"device_id": row["id"], "device_token": token, "name": row["name"]}, 200, None
        if method == "POST" and path == "/api/report":
            bearer = self.headers.get("Authorization", "")
            if not bearer.startswith("Bearer ") or len(bearer) > 200:
                raise APIError(401, "Pair this phone again.")
            row = db.execute("SELECT * FROM devices WHERE token_hash=?", (digest(bearer[7:]),)).fetchone()
            if not row:
                raise APIError(401, "This phone was disconnected. Pair it again.")
            self.server.rate_limit((row["id"], "report"), 40)
            tracking = data.get("tracking")
            if not isinstance(tracking, bool):
                raise APIError(400, "Tracking must be true or false.")
            battery = data.get("battery")
            if battery is not None and (type(battery) is not int or not 0 <= battery <= 100):
                raise APIError(400, "Invalid battery percentage.")
            loc = data.get("location")
            if loc is not None:
                if not isinstance(loc, dict):
                    raise APIError(400, "Invalid location.")
                values = [loc.get(k) for k in ("latitude", "longitude", "accuracy", "timestamp")]
                if not all(type(v) in (int, float) and math.isfinite(v) for v in values):
                    raise APIError(400, "Location needs finite latitude, longitude, accuracy and timestamp values.")
                lat, lng, accuracy, stamp = values
                if not (-90 <= lat <= 90 and -180 <= lng <= 180 and 0 <= accuracy <= 1000000 and 0 < stamp <= now + 120):
                    raise APIError(400, "Location values are out of range. Check the phone's date and time.")
                # Compare inside the write itself: concurrent reports may have
                # both read the same old row before either transaction starts.
                db.execute("UPDATE devices SET latitude=?,longitude=?,accuracy=?,located_at=? WHERE id=? AND (located_at IS NULL OR located_at<=?)",
                           (lat, lng, accuracy, stamp, row["id"], stamp))
            db.execute("UPDATE devices SET tracking=?,seen_at=?,battery=? WHERE id=?", (int(tracking), now, battery, row["id"]))
            return {"ok": True, "received_at": now}, 200, None
        user = self.user(db)
        if method == "GET" and path == "/api/me":
            return {"username": user["username"], "server_url": self.origin()}, 200, None
        if method == "POST" and path == "/api/logout":
            jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
            if "phonelink_session" in jar:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(jar["phonelink_session"].value),))
            return {"ok": True}, 200, self.session_cookie("", 0)
        if method == "GET" and path == "/api/devices":
            rows = db.execute("SELECT id,name,paired_at,pairing_expires,seen_at,tracking,latitude,longitude,accuracy,located_at,battery FROM devices WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
            return {"devices": [dict(r) for r in rows], "server_time": now}, 200, None
        if method == "POST" and path == "/api/devices":
            self.server.rate_limit((user["id"], "create"), 10)
            name = data.get("name", "")
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 50:
                raise APIError(400, "Give your phone a name (up to 50 characters).")
            if db.execute("SELECT COUNT(*) FROM devices WHERE user_id=?", (user["id"],)).fetchone()[0] >= 5:
                raise APIError(400, "You can connect up to five phones. Disconnect an old phone first.")
            device_id = secrets.token_hex(16)
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))
            db.execute("INSERT INTO devices(id,user_id,name,pairing_hash,pairing_expires,created_at) VALUES(?,?,?,?,?,?)", (device_id, user["id"], name.strip(), digest(code), now + PAIR_SECONDS, now))
            return {"id": device_id, "code": code, "expires_at": now + PAIR_SECONDS, "server_url": self.origin()}, 201, None
        match = re.fullmatch(r"/api/devices/([a-f0-9]{32})", path)
        if method == "DELETE" and match:
            deleted = db.execute("DELETE FROM devices WHERE id=? AND user_id=?", (match[1], user["id"])).rowcount
            if not deleted:
                raise APIError(404, "Phone not found.")
            return {"ok": True}, 200, None
        raise APIError(404, "Not found.")

    def static(self, path):
        files = {"/": ROOT / "web/index.html", "/app.js": ROOT / "web/app.js", "/maps.js": ROOT / "web/maps.js", "/distance.js": ROOT / "web/distance.js",
                 "/vendor/leaflet/leaflet.js": ROOT / "web/vendor/leaflet/leaflet.js",
                 "/vendor/leaflet/leaflet.css": ROOT / "web/vendor/leaflet/leaflet.css",
                 "/vendor/leaflet/LICENSE": ROOT / "web/vendor/leaflet/LICENSE",
                 "/styles.css": ROOT / "web/styles.css", "/icon.svg": ROOT / "web/icon.svg",
                 "/download/phonelink.apk": ROOT / "dist/phonelink.apk"}
        target = files.get(path)
        if not target or not target.is_file():
            raise APIError(404, "Not found. Build the APK first if you are downloading it.")
        content = target.read_bytes()
        self.send_response(200)
        self.secure_headers()
        self.send_header("Content-Type", "application/vnd.android.package-archive" if path.endswith(".apk") else (mimetypes.guess_type(target)[0] or "application/octet-stream"))
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        if path.endswith(".apk"):
            self.send_header("Content-Disposition", 'attachment; filename="phonelink.apk"')
        self.end_headers()
        self.wfile.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 to allow phones on your Wi-Fi.")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default=str(ROOT / "data/phonelink.sqlite3"))
    parser.add_argument("--public-url", default=os.environ.get("PHONELINK_PUBLIC_URL"), help="Public HTTPS origin when behind a reverse proxy.")
    args = parser.parse_args()
    server = PhoneServer((args.host, args.port), args.db, args.public_url)
    print(f"PhoneLink running at http://{args.host}:{args.port}", flush=True)
    print("For your phone, open this computer's LAN IP on the same Wi-Fi. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
