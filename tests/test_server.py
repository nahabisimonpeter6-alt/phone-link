"""Integration tests against the real HTTP server and a temporary SQLite database."""
import concurrent.futures
from contextlib import contextmanager
import http.cookiejar
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from server import PhoneServer, digest


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, body=None, method=None, headers=None):
        body = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=body, method=method,
                                         headers={"Content-Type": "application/json", **(headers or {})})
        try:
            response = self.opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        data = response.read()
        value = json.loads(data) if response.headers.get_content_type() == "application/json" else data
        status, headers = response.status, response.headers
        response.close()
        return status, value, headers


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = PhoneServer(("127.0.0.1", 0), Path(self.temp.name) / "test.sqlite3")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.owner = Client(self.base)
        status, _, _ = self.owner.request("/api/register", {"username": "owner", "password": "correct-password"})
        self.assertEqual(status, 200)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def create(self, name="My phone"):
        status, result, _ = self.owner.request("/api/devices", {"name": name})
        self.assertEqual(status, 201)
        return result

    def pair(self):
        device = self.create()
        status, result, _ = Client(self.base).request("/api/pair", {"code": device["code"]})
        self.assertEqual(status, 200)
        return device, result["device_token"]

    def report(self, token, body):
        return Client(self.base).request("/api/report", body, headers={"Authorization": "Bearer " + token})

    def devices(self, client=None):
        status, result, _ = (client or self.owner).request("/api/devices")
        self.assertEqual(status, 200)
        return result["devices"]

    def test_dashboard_and_security_headers(self):
        status, page, headers = self.owner.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"PhoneLink", page)
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertIn("https://tile.openstreetmap.org", headers["Content-Security-Policy"])
        self.assertEqual(headers["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertIn("geolocation=(self)", headers["Permissions-Policy"])
        self.assertEqual(self.owner.request("/../server.py")[0], 404)
        self.assertEqual(self.owner.request("/styles.css")[0], 200)
        self.assertEqual(self.owner.request("/app.js")[0], 200)
        for path in ("/maps.js", "/distance.js", "/vendor/leaflet/leaflet.js", "/vendor/leaflet/leaflet.css"):
            self.assertEqual(self.owner.request(path)[0], 200)

    def test_authentication_and_logout(self):
        guest = Client(self.base)
        self.assertEqual(guest.request("/api/devices")[0], 401)
        self.assertEqual(guest.request("/api/login", {"username": "owner", "password": "wrong-password"})[0], 401)
        status, _, headers = guest.request("/api/login", {"username": "owner", "password": "correct-password"})
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertEqual(guest.request("/api/me")[0], 200)
        self.assertEqual(guest.request("/api/logout", {})[0], 200)
        self.assertEqual(guest.request("/api/me")[0], 401)

    def test_weak_password_and_duplicate_username(self):
        guest = Client(self.base)
        self.assertEqual(guest.request("/api/register", {"username": "newuser", "password": "short"})[0], 400)
        self.assertEqual(guest.request("/api/register", {"username": "owner", "password": "different-password"})[0], 409)

    def test_login_requires_an_explicitly_created_account(self):
        guest = Client(self.base)
        credentials = {"username": "newcomer", "password": "newcomer-password"}
        with self.server.db() as db:
            users_before = [tuple(row) for row in db.execute("SELECT * FROM users ORDER BY id")]
            sessions_before = [tuple(row) for row in db.execute("SELECT * FROM sessions ORDER BY token_hash")]

        status, unknown_error, headers = guest.request("/api/login", credentials)
        self.assertEqual(status, 401)
        self.assertNotIn("Set-Cookie", headers)
        status, wrong_password_error, headers = guest.request("/api/login", {
            "username": "owner", "password": "wrong-password"})
        self.assertEqual(status, 401)
        self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(unknown_error, wrong_password_error)
        self.assertEqual(guest.request("/api/me")[0], 401)
        self.assertEqual(guest.request("/api/devices")[0], 401)
        with self.server.db() as db:
            self.assertEqual([tuple(row) for row in db.execute("SELECT * FROM users ORDER BY id")], users_before)
            self.assertEqual([tuple(row) for row in db.execute("SELECT * FROM sessions ORDER BY token_hash")], sessions_before)

        # The same credentials work only after the separate registration action.
        self.assertEqual(guest.request("/api/register", credentials)[0], 200)
        self.assertEqual(guest.request("/api/logout", {})[0], 200)
        viewer = Client(self.base)
        status, _, headers = viewer.request("/api/login", credentials)
        self.assertEqual(status, 200)
        self.assertIn("Set-Cookie", headers)
        self.assertEqual(viewer.request("/api/me")[1]["username"], credentials["username"])
        self.assertEqual(self.devices(viewer), [])
        with self.server.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], len(users_before) + 1)

    def test_another_browser_can_sign_in_and_receive_phone_movement(self):
        device, token = self.pair()
        self.assertEqual(self.owner.request("/api/logout", {})[0], 200)
        viewer = Client(self.base)  # A separate device has a separate cookie jar.
        self.assertEqual(viewer.request("/api/devices")[0], 401)
        self.assertEqual(viewer.request("/api/login", {
            "username": "owner", "password": "correct-password"})[0], 200)
        stamp = time.time() - 1
        for latitude, timestamp in ((.3476, stamp), (.3481, stamp + 1)):
            self.assertEqual(self.report(token, {"tracking": True, "location": {
                "latitude": latitude, "longitude": 32.583, "accuracy": 8, "timestamp": timestamp}})[0], 200)
            saved = self.devices(viewer)[0]
            self.assertEqual(saved["id"], device["id"])
            self.assertEqual(saved["latitude"], latitude)
            self.assertEqual(saved["located_at"], timestamp)
        self.assertEqual(self.owner.request("/api/devices")[0], 401)

    def test_wal_database_upgrade_preserves_account_session_and_phone(self):
        # Simulate an existing installation before the rollback-journal change.
        with self.server.db() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        device, token = self.pair()
        stamp = time.time() - 1
        self.assertEqual(self.report(token, {"tracking": True, "battery": 81,
            "location": {"latitude": .3476, "longitude": 32.583, "accuracy": 8,
                         "timestamp": stamp}})[0], 200)
        before = self.devices()[0]
        database = self.server.db_path
        with self.server.db() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")

        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.server = PhoneServer(("127.0.0.1", 0), database)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.owner.base = self.base  # Keep the original browser's session cookie.

        with self.server.db() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.owner.request("/api/me")[1]["username"], "owner")
        self.assertEqual(self.devices(), [before])
        viewer = Client(self.base)
        self.assertEqual(viewer.request("/api/login", {
            "username": "owner", "password": "correct-password"})[0], 200)
        self.assertEqual(self.devices(viewer), [before])
        self.assertEqual(self.report(token, {"tracking": True, "battery": 80,
            "location": {"latitude": .3481, "longitude": 32.583, "accuracy": 9,
                         "timestamp": stamp + 1}})[0], 200)
        saved = self.devices()[0]
        self.assertEqual(saved["id"], device["id"])
        self.assertEqual(saved["latitude"], .3481)
        self.assertEqual(saved["located_at"], stamp + 1)
        self.assertEqual(saved["battery"], 80)
        self.assertEqual(self.devices(viewer), [saved])

    def test_entire_location_flow_and_stop(self):
        device, token = self.pair()
        stamp = time.time()
        status, _, _ = self.report(token, {"tracking": True, "battery": 76,
            "location": {"latitude": .3476, "longitude": 32.5825, "accuracy": 9, "timestamp": stamp}})
        self.assertEqual(status, 200)
        saved = self.devices()[0]
        self.assertEqual(saved["id"], device["id"])
        self.assertEqual(saved["latitude"], .3476)
        self.assertEqual(saved["longitude"], 32.5825)
        self.assertEqual(saved["battery"], 76)
        self.assertEqual(saved["tracking"], 1)
        self.assertAlmostEqual(saved["located_at"], stamp)
        self.assertNotIn("token_hash", saved)
        self.assertNotIn("pairing_hash", saved)
        self.assertEqual(self.report(token, {"tracking": False})[0], 200)
        stopped = self.devices()[0]
        self.assertEqual(stopped["tracking"], 0)
        self.assertEqual(stopped["latitude"], .3476)

    def test_heartbeat_without_location(self):
        _, token = self.pair()
        self.assertEqual(self.report(token, {"tracking": True})[0], 200)
        saved = self.devices()[0]
        self.assertIsNone(saved["latitude"])
        self.assertIsNotNone(saved["seen_at"])

    def test_pairing_code_single_use_and_hash_storage(self):
        device = self.create()
        guest = Client(self.base)
        self.assertEqual(guest.request("/api/pair", {"code": device["code"]})[0], 200)
        self.assertEqual(guest.request("/api/pair", {"code": device["code"]})[0], 400)
        with self.server.db() as db:
            saved = db.execute("SELECT * FROM devices").fetchone()
            self.assertIsNone(saved["pairing_hash"])
            self.assertEqual(len(saved["token_hash"]), 64)

    def test_expired_pairing_code(self):
        device = self.create()
        with self.server.db() as db:
            db.execute("UPDATE devices SET pairing_expires=?", (time.time() - 1,))
        self.assertEqual(Client(self.base).request("/api/pair", {"code": device["code"]})[0], 400)

    def test_concurrent_pairing_only_one_wins(self):
        device = self.create()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: Client(self.base).request("/api/pair", {"code": device["code"]})[0], range(2)))
        self.assertEqual(statuses.count(200), 1)
        self.assertTrue(all(status in (200, 400, 409) for status in statuses))

    def test_accounts_cannot_read_or_disconnect_each_others_phone(self):
        device, token = self.pair()
        other = Client(self.base)
        self.assertEqual(other.request("/api/register", {"username": "other", "password": "another-password"})[0], 200)
        self.assertEqual(self.devices(other), [])
        self.assertEqual(other.request("/api/devices/" + device["id"], method="DELETE")[0], 404)
        self.assertEqual(self.report(token, {"tracking": True})[0], 200)

    def test_disconnecting_revokes_token_and_deletes_location(self):
        device, token = self.pair()
        self.assertEqual(self.owner.request("/api/devices/" + device["id"], method="DELETE")[0], 200)
        self.assertEqual(self.report(token, {"tracking": True})[0], 401)
        self.assertEqual(self.devices(), [])

    def test_old_fixes_do_not_replace_new_fixes(self):
        _, token = self.pair()
        for stamp, latitude in ((time.time(), 1), (time.time() - 3600, 2)):
            self.assertEqual(self.report(token, {"tracking": True, "location": {"latitude": latitude, "longitude": 32, "accuracy": 5, "timestamp": stamp}})[0], 200)
        self.assertEqual(self.devices()[0]["latitude"], 1)

    def test_concurrent_old_fix_cannot_overwrite_new_fix(self):
        _, token = self.pair()
        baseline = time.time() - 10
        older_stamp, newer_stamp = baseline + 1, baseline + 2
        self.assertEqual(self.report(token, {"tracking": True, "location": {
            "latitude": 0, "longitude": 32, "accuracy": 5, "timestamp": baseline}})[0], 200)
        both_read = threading.Barrier(2)
        newer_committed = threading.Event()
        original_db = self.server.db

        class ReadCursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def fetchone(self):
                row = self.cursor.fetchone()
                # Force both requests to read the original timestamp before
                # either writes. The older request then writes strictly last.
                both_read.wait(timeout=5)
                return row

        class CoordinatedDatabase:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, sql, parameters=()):
                if sql.startswith("SELECT * FROM devices WHERE token_hash="):
                    return ReadCursor(self.connection.execute(sql, parameters))
                if sql.startswith("UPDATE devices SET latitude=") and parameters[3] == older_stamp:
                    if not newer_committed.wait(timeout=5):
                        raise AssertionError("Newer location report did not finish")
                return self.connection.execute(sql, parameters)

        @contextmanager
        def coordinated_db():
            with original_db() as connection:
                yield CoordinatedDatabase(connection)

        def submit(latitude, stamp):
            try:
                return self.report(token, {"tracking": True, "location": {
                    "latitude": latitude, "longitude": 32, "accuracy": 5, "timestamp": stamp}})[0]
            finally:
                if stamp == newer_stamp:
                    # A completed HTTP response follows the database commit.
                    newer_committed.set()

        with patch.object(self.server, "db", coordinated_db):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                older = pool.submit(submit, 1, older_stamp)
                newer = pool.submit(submit, 2, newer_stamp)
                self.assertEqual(newer.result(timeout=10), 200)
                self.assertEqual(older.result(timeout=10), 200)
        saved = self.devices()[0]
        self.assertEqual(saved["latitude"], 2)
        self.assertEqual(saved["located_at"], newer_stamp)

    def test_invalid_location_reports(self):
        _, token = self.pair()
        base = {"latitude": 0, "longitude": 0, "accuracy": 5, "timestamp": time.time()}
        for key, value in (("latitude", 91), ("longitude", -181), ("accuracy", -1), ("latitude", float("nan")), ("timestamp", time.time() + 3600), ("longitude", True)):
            with self.subTest(key=key, value=value):
                self.assertEqual(self.report(token, {"tracking": True, "location": {**base, key: value}})[0], 400)
        self.assertEqual(self.report(token, {"tracking": "true"})[0], 400)
        self.assertEqual(self.report(token, {"tracking": True, "battery": 101})[0], 400)
        self.assertEqual(self.report(token, {"tracking": True, "location": []})[0], 400)

    def test_old_fix_keeps_its_original_time(self):
        _, token = self.pair()
        stamp = time.time() - 7200
        self.assertEqual(self.report(token, {"tracking": True, "location": {"latitude": 0, "longitude": 0, "accuracy": 10, "timestamp": stamp}})[0], 200)
        saved = self.devices()[0]
        self.assertEqual(saved["located_at"], stamp)
        self.assertGreater(saved["seen_at"] - saved["located_at"], 7100)

    def test_expired_session(self):
        with self.server.db() as db:
            db.execute("UPDATE sessions SET expires=?", (time.time() - 1,))
        self.assertEqual(self.owner.request("/api/me")[0], 401)

    def test_public_https_origin_sets_secure_cookie(self):
        self.server.public_url = "https://phone.example.com"
        guest = Client(self.base)
        status, _, headers = guest.request("/api/login", {"username": "owner", "password": "correct-password"},
                                            headers={"Origin": "https://phone.example.com"})
        self.assertEqual(status, 200)
        self.assertIn("; Secure", headers["Set-Cookie"])
        self.assertEqual(guest.request("/api/login", {"username": "owner", "password": "correct-password"},
                                       headers={"Origin": self.base})[0], 403)

    def test_cross_site_writes_are_rejected(self):
        self.assertEqual(self.owner.request("/api/devices", {"name": "bad"}, headers={"Origin": "https://attacker.example"})[0], 403)
        self.assertEqual(self.owner.request("/api/devices", {"name": "bad"}, headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.devices(), [])

    def test_rate_limited_pairing(self):
        guest = Client(self.base)
        for _ in range(10):
            self.assertEqual(guest.request("/api/pair", {"code": "invalid"})[0], 400)
        self.assertEqual(guest.request("/api/pair", {"code": "invalid"})[0], 429)

    def test_device_cannot_view_dashboard_with_reporting_token(self):
        _, token = self.pair()
        self.assertEqual(Client(self.base).request("/api/devices", headers={"Authorization": "Bearer " + token})[0], 401)
        self.assertEqual(self.report("wrong-token", {"tracking": True})[0], 401)


if __name__ == "__main__":
    unittest.main()
