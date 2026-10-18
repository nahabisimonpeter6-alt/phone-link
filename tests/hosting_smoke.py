#!/usr/bin/env python3
"""Exercise the real production WSGI server, persistence, recovery and concurrency.

Run with a Python environment that has requirements-deploy.txt installed.
Every account/location belongs to a temporary database, never the user's data.
"""
import concurrent.futures
import http.cookiejar
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backup import backup_database


def main():
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary)
        database = temp / 'live.sqlite3'
        origin = 'https://phone.example.test'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        cookie = ''
        log = (temp / 'server.log').open('a')
        process = None

        def start(db):
            env = {**os.environ, 'PHONELINK_PUBLIC_URL': origin, 'PHONELINK_DB': str(db)}
            child = subprocess.Popen([sys.executable, 'serve.py', '--port', str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                try:
                    if request('/api/health', use_cookie=False)[0] == 200: return child
                except OSError: pass
                if child.poll() is not None:
                    raise AssertionError('Production server failed to start: ' + (temp / 'server.log').read_text())
                time.sleep(.1)
            child.terminate(); child.wait(timeout=5)
            raise AssertionError('Production server did not become healthy')

        def stop(crash=False):
            nonlocal process
            if process and process.poll() is None:
                if crash: process.kill()
                else: process.terminate()
                process.wait(timeout=5)
            process = None

        def request(path, body=None, method=None, token=None, use_cookie=True):
            headers = {'Content-Type': 'application/json', 'Origin': origin}
            if use_cookie and cookie: headers['Cookie'] = cookie
            if token: headers['Authorization'] = 'Bearer ' + token
            req = urllib.request.Request(base + path, method=method, headers=headers,
                data=json.dumps(body).encode() if body is not None else None)
            try: response = urllib.request.urlopen(req, timeout=10)
            except urllib.error.HTTPError as error: response = error
            with response:
                value = response.read()
                if value and response.headers.get_content_type() == 'application/json': value = json.loads(value)
                return response.status, value, response.headers

        try:
            process = start(database)
            status, _, headers = request('/api/register', {'username': 'host-test', 'password': 'hosting-test-password'})
            assert status == 200
            assert '; Secure' in headers['Set-Cookie'] and 'HttpOnly' in headers['Set-Cookie']
            # The browser connects to HTTPS in production. This test talks to the
            # internal HTTP WSGI port, so it forwards the proxy-side cookie itself.
            cookie = headers['Set-Cookie'].split(';')[0]
            tokens, ids = [], []
            for index in range(5):
                status, entry, _ = request('/api/devices', {'name': f'Test phone {index}'})
                assert status == 201
                status, paired, _ = request('/api/pair', {'code': entry['code']}, use_cookie=False)
                assert status == 200
                tokens.append(paired['device_token'])
                ids.append(entry['id'])

            def hit(index):
                started = time.monotonic()
                if index < 100:
                    status, _, _ = request('/api/report', {'tracking': True, 'battery': 80,
                        'location': {'latitude': .3476 + index / 100000, 'longitude': 32.5825, 'accuracy': 10, 'timestamp': time.time()}}, token=tokens[index % 5], use_cookie=False)
                else:
                    status, _, _ = request('/api/devices')
                return status, time.monotonic() - started

            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(hit, range(200)))
            assert all(status == 200 for status, _ in results), f'Request errors: {[s for s, _ in results if s != 200]}'
            latencies = sorted(duration for _, duration in results)
            print(f'PASS: 200 requests, 12 concurrent clients, 0 HTTP errors; p95 {latencies[int(len(latencies)*.95)-1]*1000:.1f} ms')

            status, before, _ = request('/api/devices')
            assert status == 200 and len(before['devices']) == 5
            assert all(device['located_at'] for device in before['devices'])
            backup = backup_database(database, temp / 'backup.sqlite3')
            assert backup.stat().st_mode & 0o777 == 0o600
            try:
                backup_database(database, backup)
                raise AssertionError('Existing backup was overwritten')
            except ValueError: pass
            stop(crash=True); process = start(database)
            status, after, _ = request('/api/devices')
            assert status == 200 and before['devices'] == after['devices']
            assert request('/api/report', {'tracking': False}, token=tokens[0], use_cookie=False)[0] == 200
            print('PASS: accounts, sessions, device credentials and committed locations survive a forced process kill and restart')

            stop(); process = start(backup)
            status, restored, _ = request('/api/devices')
            assert status == 200 and restored['devices'] == before['devices']
            assert request('/api/report', {'tracking': True}, token=tokens[0], use_cookie=False)[0] == 200
            print('PASS: verified live SQLite backup restores the account, paired phones, tokens and coordinates')

            assert request('/api/health', method='HEAD')[0] == 200
            assert request('/api/health', method='PUT')[0] == 405
            assert request('/api/devices', use_cookie=False)[0] == 401
            for path in ('/', '/maps.js', '/distance.js', '/vendor/leaflet/leaflet.js', '/vendor/leaflet/leaflet.css', '/download/phonelink.apk'):
                assert request(path)[0] == 200
            assert request('/api/devices/' + ids[0], method='DELETE')[0] == 200
            assert request('/api/report', {'tracking': True}, token=tokens[0], use_cookie=False)[0] == 401
            print('PASS: production static assets, APK download, health, HEAD, access checks and token revocation')
        finally:
            stop(); log.close()


if __name__ == '__main__': main()
