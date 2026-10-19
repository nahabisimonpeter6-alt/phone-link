#!/usr/bin/env python3
"""Optional real-Firefox UI flow. Uses geckodriver; no Python dependencies.

Run: python3 tests/browser_smoke.py
Install Mozilla's geckodriver in PATH or .tools/geckodriver first.
All accounts and synthetic locations stay in a temporary test database.
"""
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import PhoneServer


def main():
    gecko = os.environ.get("GECKODRIVER") or shutil.which("geckodriver") or str(ROOT / ".tools/geckodriver")
    if not Path(gecko).is_file(): raise SystemExit("Install geckodriver first; see this script's docstring.")
    with tempfile.TemporaryDirectory() as temp:
        server = PhoneServer(("127.0.0.1", 0), Path(temp) / "ui.sqlite3")
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        (ROOT / ".tools").mkdir(exist_ok=True)
        log = (ROOT / ".tools/browser.log").open("w")
        process = subprocess.Popen([gecko, "--host", "127.0.0.1", "--port", str(port), "--profile-root", str(ROOT / ".tools")], stdout=log, stderr=log)
        driver_url = f"http://127.0.0.1:{port}"
        session = None

        def wd(method, path, data=None):
            request = urllib.request.Request(driver_url + path, method=method,
                data=json.dumps(data).encode() if data is not None else None,
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response: return json.load(response)["value"]
            except urllib.error.HTTPError as error:
                raise AssertionError(error.read().decode()) from error

        def cmd(path, data=None, method="POST"):
            return wd(method, f"/session/{session}" + path, data)

        def script(source, *args):
            return cmd("/execute/sync", {"script": source, "args": list(args)})

        def wait(source, timeout=15):
            until = time.monotonic() + timeout
            while time.monotonic() < until:
                result = script("return " + source)
                if result: return result
                time.sleep(.15)
            screenshot('browser-failure.png')
            details = script("return {zoom:window.testStreetZoom, maps:Array.from(document.querySelectorAll('.phone-map')).map(m=>({rect:m.getBoundingClientRect().toJSON(),pane:m.querySelector('.leaflet-map-pane')?.style.cssText})), tiles:Array.from(document.querySelectorAll('.leaflet-tile')).map(t=>({src:t.src,complete:t.complete,width:t.naturalWidth,opacity:getComputedStyle(t).opacity})),message:document.querySelector('.map-message')?.textContent}")
            (ROOT / '.tools/browser-failure.json').write_text(json.dumps(details, indent=2))
            raise AssertionError("Timed out waiting for: " + source)

        def click(selector):
            script("document.querySelector(arguments[0]).click()", selector)

        def fill(selector, value):
            script("const e=document.querySelector(arguments[0]); e.value=arguments[1]; e.dispatchEvent(new Event('input',{bubbles:true}));", selector, value)

        def screenshot(name):
            (ROOT / "dist").mkdir(exist_ok=True)
            (ROOT / "dist" / name).write_bytes(base64.b64decode(cmd("/screenshot", method="GET")))

        def api(path, body, token=None):
            headers = {"Content-Type": "application/json"}
            if token: headers["Authorization"] = "Bearer " + token
            request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}" + path,
                data=json.dumps(body).encode(), headers=headers)
            with urllib.request.urlopen(request, timeout=10) as response: return json.load(response)

        def directions():
            return script("const a=document.querySelector('.directions-link'); const url=new URL(a.href); return {origin:url.origin,path:url.pathname,params:Object.fromEntries(url.searchParams),text:a.textContent,rel:a.rel,target:a.target};")

        try:
            for _ in range(100):
                try:
                    wd("GET", "/status"); break
                except Exception: time.sleep(.1)
            else: raise AssertionError("geckodriver did not start; see .tools/browser.log")
            capabilities = {"browserName": "firefox", "moz:firefoxOptions": {"args": ["-headless"]}}
            binary = os.environ.get("FIREFOX_BIN")
            if not binary and Path("/snap/firefox/current/usr/lib/firefox/firefox").is_file():
                binary = "/snap/firefox/current/usr/lib/firefox/firefox"
            if binary: capabilities["moz:firefoxOptions"]["binary"] = binary
            session = wd("POST", "/session", {"capabilities": {"alwaysMatch": capabilities}})["sessionId"]
            cmd("/window/rect", {"width": 1440, "height": 1050})
            cmd("/url", {"url": f"http://127.0.0.1:{server.server_port}"})
            wait("!document.querySelector('#auth-view').hidden")
            screenshot("login.png")
            assert script("return document.querySelector('#auth-description').textContent.includes('already created')")
            assert script("return document.querySelector('#confirm-password').disabled")
            fill("#username", "browser-test"); fill("#password", "browser-test-password")
            click('#auth-submit')
            wait("!document.querySelector('#auth-error').hidden && !document.querySelector('#auth-submit').disabled")
            assert script("return document.querySelector('#dashboard').hidden && !document.querySelector('#auth-view').hidden"), 'Unknown account reached dashboard'
            with server.db() as database:
                assert database.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
                assert database.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
            click("#auth-switch")
            assert script("return document.querySelector('#password').value") == '', 'Mode switch retained password'
            assert not script("return document.querySelector('#confirm-password-field').hidden")
            fill("#password", "browser-test-password"); fill('#confirm-password', 'different-password')
            click('#auth-submit')
            wait("document.querySelector('#auth-error').textContent.includes('do not match')")
            with server.db() as database:
                assert database.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
            fill('#confirm-password', 'browser-test-password')
            click("#auth-submit")
            wait("!document.querySelector('#dashboard').hidden && !document.querySelector('#empty-state').hidden")
            click("#add-phone"); fill("#phone-name", "Test Android <safe>"); click("#create-code")
            wait("!document.querySelector('#pair-details').hidden")
            assert script("return document.querySelector('#server-address').value") == '', 'Localhost address was offered to a physical phone'
            assert script("return document.querySelector('#copy-server-address').disabled"), 'Localhost copy was enabled'
            assert script("return document.querySelector('#server-address-note').textContent.includes('Localhost on a phone')")
            script("showPairServerAddress('https://tracker.example.test')")
            assert script("return document.querySelector('#server-address').value") == 'https://tracker.example.test'
            assert not script("return document.querySelector('#copy-server-address').disabled"), 'Hosted address could not be copied'
            script("showPairServerAddress(location.origin)")
            code = script("return document.querySelector('#pair-code').value")
            paired = api("/api/pair", {"code": code})
            api("/api/report", {"tracking": True,
                "location": {"latitude": .3476, "longitude": 32.5825, "accuracy": 8, "timestamp": time.time() - 120}}, paired["device_token"])
            wait("document.querySelector('.badge')?.textContent === 'Last known'")
            api("/api/report", {"tracking": True, "battery": 85,
                "location": {"latitude": .3476, "longitude": 32.5825, "accuracy": 8, "timestamp": time.time()}}, paired["device_token"])
            wait("document.querySelector('.badge')?.textContent === 'Live'")
            wait("document.querySelector('.phone-map .leaflet-marker-icon')")
            assert script("return document.querySelector('.phone-map .leaflet-control-attribution').textContent").find('OpenStreetMap') >= 0
            assert not script("return document.querySelector('.phone-map-pin').classList.contains('is-stale')")
            script("window.testMapNode=document.querySelector('.phone-map'); window.testCardNode=document.querySelector('.device-card'); window.testTileNodes=Array.from(document.querySelectorAll('.leaflet-tile')); window.testTileSources=testTileNodes.map(e=>e.src)")
            # A second fix must move the existing map marker, without rebuilding
            # the map or discarding tiles on every dashboard refresh.
            api("/api/report", {"tracking": True, "battery": 84,
                "location": {"latitude": .3481, "longitude": 32.5830, "accuracy": 12, "timestamp": time.time()}}, paired["device_token"])
            wait("document.querySelector('.phone-map-pin')?.title.includes('0.34810, 32.58300')")
            assert script("return window.testMapNode === document.querySelector('.phone-map')")
            assert script("return window.testCardNode === document.querySelector('.device-card')"), 'Polling detached the map card'
            assert script("return window.testTileNodes.some(node=>node.isConnected)"), 'Map unnecessarily replaced its tiles'
            assert script("return document.querySelector('.device-name').textContent") == "Test Android <safe>"
            assert script("return document.querySelector('.device-bottom a').href").startswith("https://www.google.com/maps/search/?api=1&query=")
            assert script("return document.querySelector('.coordinates').textContent") == "0.34810, 32.58300"
            assert script("return document.querySelector('.follow-phone').getAttribute('aria-pressed')") == 'true'
            assert script("return document.querySelector('.phone-map svg path') !== null"), 'Accuracy circle is missing'
            route = directions()
            assert route['origin'] == 'https://www.google.com' and route['path'] == '/maps/dir/'
            assert route['params'] == {'api': '1', 'destination': '0.3481,32.583'}, 'Directions must use latest phone fix, with no stale viewer origin'
            assert route['target'] == '_blank' and 'noopener' in route['rel'] and 'noreferrer' in route['rel']
            assert 'travel time' in route['text']
            assert script("return ViewerDistance.directionsUrl({latitude:91,longitude:0})") is None
            # Known spherical distances test the calculation independently of
            # location permissions, including zero and crossing the date line.
            assert script("return ViewerDistance.distanceMetres(0,0,0,0)") == 0
            assert abs(script("return ViewerDistance.distanceMetres(0,0,1,0)") - 111195.0802) < .1
            assert abs(script("return ViewerDistance.distanceMetres(0,179,0,-179)") - 222390.1605) < .1
            assert script("return ViewerDistance.distanceMetres(91,0,0,0)") is None
            # Use controlled browser geolocation callbacks so permission/error/
            # movement cases are reproducible without uploading the viewer fix.
            script("""window.testClearWatches=0; window.testViewerPosts=[]; window.testViewerFetches=[];
              window.originalTestFetch=window.fetch;
              window.fetch=(url,options={})=>{testViewerFetches.push(String(url));if(options.method==='POST')testViewerPosts.push(options.body);return originalTestFetch(url,options)};
              Object.defineProperty(navigator,'geolocation',{configurable:true,value:{
                watchPosition:(success,error)=>{window.testViewerFix=success;window.testViewerError=error;return 77},
                clearWatch:()=>window.testClearWatches++}});""")
            click('#distance-toggle')
            wait("document.querySelector('.distance-value')?.textContent === 'Locating you…'")
            script("testViewerFix({coords:{latitude:.3381,longitude:32.5830,accuracy:10},timestamp:Date.now()})")
            wait("document.querySelector('.distance-value')?.textContent === 'About 1.1 km'")
            assert directions()['params']['origin'] == '0.3381,32.583'
            # A hidden tab need not rerender when the viewer fix expires. Each
            # normal way to open directions must recheck freshness at activation.
            activation_checks = script("""const a=document.querySelector('.directions-link'); const realNow=window.Date.now;
              try {
                return ['click','auxclick','contextmenu'].map(type=>{
                  window.Date.now=realNow;
                  a.href=ViewerDistance.directionsUrl({latitude:.3481,longitude:32.583});
                  const before=new URL(a.href).searchParams.get('origin');
                  window.Date.now=()=>realNow()+61000;
                  a.addEventListener(type,e=>e.preventDefault(),{once:true});
                  a.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,button:type==='click'?0:1}));
                  return {type,before,after:new URL(a.href).searchParams.get('origin')};
                });
              } finally { window.Date.now=realNow; }""")
            assert all(check['before'] and check['after'] is None for check in activation_checks), f'Directions activation shared an expired viewer fix: {activation_checks}'
            script("testViewerFix({coords:{latitude:.3431,longitude:32.5830,accuracy:10},timestamp:Date.now()})")
            wait("document.querySelector('.distance-value')?.textContent === 'About 556 m'")
            assert directions()['params']['origin'] == '0.3431,32.583', 'Directions retained an old viewer fix'
            api('/api/report', {'tracking': True, 'location': {'latitude': .3491, 'longitude': 32.5830, 'accuracy': 12, 'timestamp': time.time()}}, paired['device_token'])
            wait("document.querySelector('.distance-value')?.textContent === 'About 667 m'")
            assert directions()['params']['destination'] == '0.3491,32.583', 'Directions retained an old destination'
            api('/api/report', {'tracking': True, 'location': {'latitude': .3481, 'longitude': 32.5830, 'accuracy': 12, 'timestamp': time.time()}}, paired['device_token'])
            wait("document.querySelector('.distance-value')?.textContent === 'About 556 m'")
            script("testViewerFix({coords:{latitude:.3431,longitude:32.5830,accuracy:10},timestamp:Date.now()-61000})")
            wait("document.querySelector('.distance-value')?.textContent.includes('Waiting for your current')")
            assert 'origin' not in directions()['params'], 'Directions used a stale viewer fix'
            script("testViewerFix({coords:{latitude:.3431,longitude:32.5830,accuracy:10},timestamp:Date.now()+60000})")
            assert 'origin' not in directions()['params'], 'Directions used a future viewer fix'
            script("testViewerError({code:1})")
            wait("document.querySelector('#distance-status').textContent.includes('denied')")
            assert script("return document.querySelector('#distance-toggle').getAttribute('aria-pressed')") == 'false'
            assert 'origin' not in directions()['params'], 'Denied location remained in directions'
            script('window.testOldViewerFix=window.testViewerFix')
            click('#distance-toggle')
            script("testOldViewerFix({coords:{latitude:2,longitude:33,accuracy:10},timestamp:Date.now()})")
            assert 'origin' not in directions()['params'], 'Canceled watcher leaked an old origin'
            script('testViewerError({code:3})')
            wait("document.querySelector('#distance-status').textContent.includes('timed out')")
            assert 'origin' not in directions()['params']
            script("testViewerFix({coords:{latitude:.3431,longitude:32.5830,accuracy:10},timestamp:Date.now()})")
            wait("document.querySelector('.distance-value')?.textContent === 'About 556 m'")
            assert script("return window.testViewerPosts.length") == 0, 'Viewer location triggered a POST'
            assert script("return window.testViewerFetches.every(url=>url.startsWith('/api/'))"), 'Dashboard sent a route/location request to an external service'
            assert script("return Object.keys(localStorage).length + Object.keys(sessionStorage).length") == 0
            # Actual pointer dragging stops follow mode; the button restores it.
            point = script("const r=document.querySelector('.phone-map').getBoundingClientRect(); return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}")
            cmd('/actions', {'actions': [{'type': 'pointer', 'id': 'map-mouse', 'parameters': {'pointerType': 'mouse'}, 'actions': [
                {'type': 'pointerMove', 'duration': 0, 'x': point['x'], 'y': point['y']}, {'type': 'pointerDown', 'button': 0},
                {'type': 'pointerMove', 'duration': 300, 'x': point['x'] + 80, 'y': point['y']}, {'type': 'pointerUp', 'button': 0}]}]})
            wait("document.querySelector('.follow-phone').getAttribute('aria-pressed') === 'false'")
            click('.follow-phone')
            wait("document.querySelector('.follow-phone').getAttribute('aria-pressed') === 'true'")
            visible_tiles = "Array.from(document.querySelectorAll('.phone-map .leaflet-tile')).some(tile => { const t=tile.getBoundingClientRect(); const m=document.querySelector('.phone-map').getBoundingClientRect(); return tile.complete && tile.naturalWidth>=256 && Number(getComputedStyle(tile).opacity)>.9 && t.right>m.left && t.left<m.right && t.bottom>m.top && t.top<m.bottom; })"
            wait(visible_tiles)
            script("window.testStreetZoom=Math.max(...Array.from(document.querySelectorAll('.phone-map .leaflet-tile')).map(t=>Number(new URL(t.src).pathname.split('/')[1])))")
            click('.leaflet-control-zoom-in')
            wait("Array.from(document.querySelectorAll('.phone-map .leaflet-tile')).some(tile=>Number(new URL(tile.src).pathname.split('/')[1]) > window.testStreetZoom && tile.complete && tile.naturalWidth>0 && Number(getComputedStyle(tile).opacity)>.9)")
            click('.leaflet-control-zoom-out')
            wait("!document.querySelector('#pair-dialog').open")
            screenshot("dashboard.png")
            cmd("/window/rect", {"width": 390, "height": 844})
            wait("(() => {const map=document.querySelector('.phone-map').getBoundingClientRect(); const pin=document.querySelector('.phone-map-pin').getBoundingClientRect(); return Math.abs(pin.x+pin.width/2-map.x-map.width/2)<5 && Math.abs(pin.y+pin.height/2-map.y-map.height/2)<5})()")
            wait(visible_tiles)
            assert script("return document.documentElement.scrollWidth <= window.innerWidth"), "Mobile page overflows horizontally"
            screenshot("dashboard-mobile.png")
            api("/api/report", {"tracking": False}, paired["device_token"])
            wait("document.querySelector('.badge')?.textContent === 'Sharing stopped'")
            assert script("return document.querySelector('.distance-label').textContent") == 'Distance to last known position'
            assert 'last known position' in directions()['text'], 'Stopped phone directions were presented as current'
            click('#distance-toggle')
            wait("document.querySelector('.distance-value')?.textContent === 'Enable your location'")
            assert 'origin' not in directions()['params'], 'Stop distance retained the viewer origin'
            assert script("return window.testClearWatches >= 2")
            assert script("return document.querySelector('.phone-map-pin').classList.contains('is-stale')")
            # Disconnect the actual test backend, verify the browser preserves
            # the last fix with a warning, then recover on the same URL/database.
            port = server.server_port
            server.shutdown(); server.server_close(); thread.join()
            wait("!document.querySelector('#dashboard-error').hidden")
            assert script("return document.querySelector('.coordinates').textContent") == '0.34810, 32.58300'
            server = PhoneServer(('127.0.0.1', port), Path(temp) / 'ui.sqlite3')
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            wait("document.querySelector('#dashboard-error').hidden")
            assert script("return document.querySelector('.device-name').textContent") == 'Test Android <safe>'
            click(".disconnect"); click("#confirm-disconnect")
            wait("!document.querySelector('#empty-state').hidden")
            assert script("return document.querySelectorAll('.phone-map').length") == 0
            click("#logout")
            wait("!document.querySelector('#auth-view').hidden")
            fill("#username", "browser-test"); fill("#password", "browser-test-password"); click("#auth-submit")
            wait("!document.querySelector('#dashboard').hidden")
            print("PASS: Firefox unknown-account login rejection, explicit registration/password confirmation, localhost pairing guard/hosted address, real map, zoom, movement, accuracy, mobile layout, viewer/phone distance updates, Google Maps directions with current destination/fresh origin, stale/future viewer fixes, denial/timeout/canceled watcher, viewer privacy, stop/recovery, pairing and login.")
            print("Screenshots: dist/login.png, dist/dashboard.png, dist/dashboard-mobile.png (synthetic test data only)")
        finally:
            if session:
                try: wd("DELETE", "/session/" + session)
                except Exception: pass
            try:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            except (PermissionError, ProcessLookupError):
                # Some Snap launchers detach into a different security namespace.
                # DELETE /session already closes the browser and its test profile.
                pass
            finally:
                log.close(); server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__": main()
