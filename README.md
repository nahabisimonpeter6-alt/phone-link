# PhoneLink

A small Android phone tracker with a private web dashboard and a live street map. No API keys, paid map SDK, Firebase or Node.js are required. The local server uses Python's standard library; the optional production launcher adds the small Waitress package.

**The phone must be paired and sharing its location before it goes missing.** Registration details, phone numbers and IMEIs cannot locate an unprepared phone. This app does not access police or mobile-operator tracking systems.

## Run the dashboard

Requires Python 3.10 or later with SQLite and `hashlib.scrypt` support (standard on normal Python installations).

```bash
python3 server.py --host 0.0.0.0 --port 8080
```

On this computer open **http://localhost:8080**. Create an account with a username and password of at least 10 characters. There is no email verification or password reset in this small version; keep your password safe.

Find this computer’s Wi-Fi IP address:

```bash
hostname -I
```

Use the Wi-Fi address, for example **http://192.168.1.10:8080**, on the phone. Both devices must be on the same network for this local setup. A phone’s `localhost` refers to the phone, not your computer. If access fails, check the computer’s firewall and Wi-Fi client isolation. The server defaults to localhost only unless `--host 0.0.0.0` is supplied.

## Install and connect the Android APK

Build the APK with `python3 android/build.py` first (see [Build the APK](#build-the-apk)). Build output is excluded from Git: when moving to a new host, build there or privately copy **dist/phonelink.apk** from your build computer to the same path on the host. The server serves it at **http://localhost:8080/download/phonelink.apk**. Open the website using the computer’s Wi-Fi IP on your phone to download it. Allow installation from that browser when Android asks.

1. On the dashboard click **Connect a phone**, name it, and create a pairing code.
2. In the APK enter the same server address and the pairing code. Codes are single-use and expire after 10 minutes. If you generated the code at `localhost`, replace the server address with the computer’s Wi-Fi IP when entering it in the APK.
3. Tap **Connect phone**. Then tap **Start tracking**, allow location access (Precise is recommended) and notifications. Keep the phone’s Location setting on.
4. Check the dashboard from another device. The street map shows a phone pin and an accuracy circle. It refreshes every 5 seconds; the APK attempts a report about every 15 seconds. New fixes move the same pin without resetting your zoom or reloading the whole map. Drag to explore; **Follow phone** recenters and resumes following. The intervals are best effort, subject to GPS, connectivity, Android power management and the phone manufacturer.
5. **Open in Google Maps** opens the last received coordinates. **Route & travel time in Google Maps** opens directions to that position: Google Maps shows route distance and estimated travel time, and lets you choose walking or driving. No API key is needed for these [Google Maps URLs](https://developers.google.com/maps/documentation/urls/get-started). The external destination is a snapshot; reopen directions if the phone moves. For an old/stopped fix the button explicitly says **last known position**.

To see the distance from the device viewing the dashboard to a tracked phone, tap **Show my distance** and allow browser location access. The distance is an approximate **straight-line** measurement, not road/travel distance. It updates as either device moves, shows meters/kilometers and both locations' reported accuracy, and changes to **Distance to last known position** for an old/stopped phone fix. A viewer fix older than one minute is not used as a current position. **Stop distance** clears the viewer's position and stops its location watch. Signing out also clears it.

The viewer's location stays in page memory: it is not uploaded to PhoneLink, saved in the database or stored in browser storage. Opening directions shares the phone's destination and, if enabled and fresh, the viewer's starting coordinates with Google Maps. Without a fresh viewer fix the link leaves the starting point for Google Maps to determine or ask for. The dashboard does not call a routing service automatically. Route length and travel time appear **in Google Maps**; the dashboard's own distance remains straight-line distance, with no invented travel time or traffic estimate.

Browser location needs HTTPS (or localhost for desktop testing). Opening a plain `http://192.168...`/`http://10...` address is enough for the street map but cannot provide the viewing device's position; deploy HTTPS for phone-to-phone distance. Both devices need location access and internet; the tracked phone also needs the paired APK sharing. Location being on alone cannot locate an unpaired or stopped phone. GPS accuracy and internet availability still apply.

Android **8.0+** is supported. Sharing runs in a location foreground service, with a visible notification and Stop action. The app requests no background-location permission: start it while the activity is visible, then the existing foreground service can continue while the screen is locked. After a reboot, force-stop, app removal, or an Android stop action, open the APK and start tracking again. Some manufacturers need an additional “Unrestricted” battery setting under Apps → PhoneLink → Battery for reliable screen-off operation.

The APK keeps only the latest fix while offline, retries automatically, and includes the fix’s original timestamp. The dashboard shows **Last known** after 60 seconds without a fresh fix. A heartbeat cannot make an old location look live. Stop sharing in the APK or notification. Disconnecting a phone on the website deletes its saved location and revokes its reporting token. Unpairing in the APK removes the local credentials; remove its entry on the website to delete the server copy too.

The live map uses self-hosted [Leaflet 1.9.4](https://leafletjs.com/) (BSD-2-Clause license in `web/vendor/leaflet/LICENSE`) and [OpenStreetMap](https://www.openstreetmap.org/copyright) street tiles. No map key is needed. Street tiles need internet access and are a best-effort shared service with no uptime guarantee. The implementation keeps attribution visible, uses normal browser caching, and does not prefetch or download maps for offline use, following the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/). Tile requests go directly from the viewer’s browser to OpenStreetMap and reveal the viewed map area and viewer IP to that provider; account credentials and device tokens are not sent. The Referer is limited to the website’s origin. If tiles fail, the coordinates, timestamps and external Google Maps link remain available. This map follows location reports; use Google Maps for route navigation.

## Track away from this Wi-Fi

For a lost phone to report over mobile data, the backend needs a stable, internet-reachable **HTTPS** address. A local-only server cannot receive reports after the phone leaves the network.

For hosting, use the production WSGI entry point. A provider such as PythonAnywhere can load `wsgi.application` directly; set `PHONELINK_PUBLIC_URL` and `PHONELINK_DB` in its WSGI configuration before importing it. The database must be on persistent private storage. It must not be under the public static directory.

For a server that runs your own processes, install the small hosting dependency and use Waitress behind your HTTPS reverse proxy:

```bash
python3 -m pip install -r requirements-deploy.txt
export PHONELINK_PUBLIC_URL=https://phone.example.com
export PHONELINK_DB=/absolute/persistent/path/phonelink.sqlite3
python3 serve.py --host 127.0.0.1 --port 8080
```

Forward that HTTPS origin to `127.0.0.1:8080`. The static website and API share this origin. The public origin sets Secure cookies and browser origin checks. Configure the reverse proxy to enforce HTTPS, reject unexpected Host headers, cap request bodies, and limit traffic. Bind Python to loopback when a proxy runs on the same machine. Waitress runs eight request threads and bounds connections, headers and request bodies. If the proxy strips untrusted forwarded headers, set `PHONELINK_TRUSTED_PROXY` to its known IP for accurate client IP rate limits. Do not set it to `*`. On managed WSGI hosting, use the platform's documented client-IP handling instead.

Configure the host's process manager to restart on failure and after reboot, and monitor `GET /api/health`. That endpoint checks that the database schema is readable. A successful local test is not a guarantee of uptime on an untested host. See [TEST_REPORT.md](TEST_REPORT.md) for the current verification and remaining device/hosting checks.

Before moving or updating the app, make a consistent backup (safe while it is running):

```bash
python3 backup.py
```

The command uses the configured `PHONELINK_DB`, or the default local database, and saves a private, integrity-checked copy under `data/backups/`. Existing backups are not overwritten. Download backups to a separate private location; a backup kept only on the host cannot protect against losing the whole host. To restore, stop the server and set `PHONELINK_DB` to a copy of a verified backup. Never publish database backups. For a small deployment use one application process; multiple server processes would have separate in-memory rate limits.

You can also use a temporary HTTPS tunnel for a demonstration, then pair using its HTTPS address. A changed tunnel URL requires re-pairing. Never send account passwords or location reports over public plain HTTP; the APK accepts HTTP only for localhost/private IPv4 addresses. Local HTTP is for a trusted test Wi-Fi. The Android manifest permits cleartext for this local setup, while the client rejects public HTTP destinations and does not follow redirects with credentials.

The software has no service charges or API keys. Continuous remote availability still requires an always-on host, internet, power and phone data. Self-host on equipment you already have, or use a provider’s free allowance after checking its current limits. No third-party free hosting or uninterrupted recovery is guaranteed. There is no pretend live-location demo in the dashboard; it waits for real reports.

## Build the APK

Requires Linux x86-64, Python 3 and OpenJDK **21**. Downloaded SDK tools require standard Linux runtime libraries. The first build downloads about 126 MB of official Android SDK packages from Google and verifies their published SHA-1 checksums. Their included Android SDK license files apply. No Gradle or cloud build account is required.

```bash
python3 android/build.py
```

The build compiles Java sources against Android API 35, creates DEX with `d8`, packages resources with `aapt2`, aligns, signs, and verifies the APK. The result is `dist/phonelink.apk`. Local SDK files and a **development signing key** are cached in `.tools/` and ignored by Git. Keep this key if you want to install updates over this build. Its conventional development password is not suitable for public production releases. Use a private release signing key for public distribution.

## Verify

```bash
python3 -m unittest discover -s tests -v
python3 tests/browser_smoke.py
python3 android/build.py
python3 -m pip install -r requirements-deploy.txt
python3 tests/hosting_smoke.py
```

The integration suite uses a real HTTP server and a temporary database to check sign-in from another browser session after the original signs out, owner isolation, one-use/expired pairing, concurrent pairing, location validation, sequential and concurrent out-of-order fixes, offline timestamps, stop sharing, revocation, expired sessions, origin checks, rate limits and static assets.

For the optional real-browser flow, install Firefox and [Mozilla geckodriver](https://github.com/mozilla/geckodriver/releases) in your PATH (or `.tools/geckodriver`), then run `python3 tests/browser_smoke.py`. It checks desktop/mobile rendering, registration/login, pairing, stale/live fixes, map marker movement, tile reuse, attribution, the accuracy circle, viewer/phone distance updates and Google Maps directions. It verifies that directions use the latest destination, omit stale/future/denied/stopped viewer origins, and make no automatic external routing request. Stopping and disconnection are covered too. Its synthetic coordinates use a temporary database; screenshots are saved under `dist/`.

`hosting_smoke.py` needs the hosting dependency installed. It launches real Waitress processes on localhost with temporary databases, runs 200 concurrent-client requests, restarts the process, restores a backup and checks private access, reporting tokens, static map assets and APK downloads. It simulates the internal side of an HTTPS reverse proxy; it does not certify an external host's TLS or uptime. The browser test uses Firefox/geckodriver as described above, including a real backend outage and recovery.

On a real Android phone, also verify: initial pairing; precise/approximate/denied permissions; a GPS fix outdoors; a 10-minute screen-lock test; network loss and recovery; location disabled; Stop in the notification; force-stop/restart; and revocation from the website. An APK build and backend tests alone do not verify device-specific background behavior.

## Files and data

- `server.py`: Python standard-library HTTP API and SQLite relay.
- `wsgi.py`, `serve.py`: production hosting interface and optional Waitress launcher.
- `backup.py`: verified live SQLite backups.
- `web/`: plain HTML, CSS and JavaScript dashboard with a vendored Leaflet map library; no runtime script/CDN dependencies. Street tiles come from OpenStreetMap.
- `android/`: native Android Java sources and reproducible build script.
- `data/phonelink.sqlite3`: generated database; back it up privately if needed. It contains password hashes, hashed session/device/pairing tokens and each phone’s **latest** location. There is no location history.

## API

Requests and responses are JSON. Browser access uses an HttpOnly, SameSite=Strict session cookie. It becomes Secure with an HTTPS `--public-url`. Device credentials can report only; they cannot read dashboard locations.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/register`, `/api/login` | `{username, password}` → browser session |
| `POST /api/logout` | End the current session |
| `GET /api/me` | Current account and server address |
| `GET /api/devices` | This account’s phones and latest locations |
| `POST /api/devices` | `{name}` → pending phone, one-time `code`, expiry, server address |
| `DELETE /api/devices/{id}` | Remove this account’s phone and revoke its token |
| `POST /api/pair` | `{code}` → `device_id`, `device_token`, `name` |
| `POST /api/report` | Device bearer token + `{tracking, battery?, location?}` |
| `GET /api/health` | Health check without account data |

`location` contains `latitude`, `longitude`, `accuracy` in meters and `timestamp` in Unix **seconds** of the GPS/network fix. Server receipt time is separate. Older fixes never overwrite newer ones. The dashboard’s Live label requires active sharing, a report within 60 seconds, and a location fix within 60 seconds. Paired phones are limited to five per account to keep this deployment small.
