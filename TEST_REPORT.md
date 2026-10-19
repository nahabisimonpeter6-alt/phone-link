# PhoneLink verification report

**Result:** The tested web map, API, production server and recovery scenarios pass. This is ready for a real-device pilot, not a guarantee of uninterrupted lost-phone recovery. A physical Android test and a public HTTPS deployment test remain.

Last retested: 19 October 2026 (Africa/Kampala).

## Verified results

| Area | Result | Evidence |
| --- | --- | --- |
| API and access controls | PASS | 22 integration tests against real HTTP and SQLite |
| Account creation required | PASS | Unknown-account/wrong-password login rejects access, issues no session cookie and leaves users/sessions unchanged; only explicit registration creates the account |
| Sign-in page | PASS | Clear existing-account instructions, registration password confirmation, mismatched passwords rejected before account creation, passwords cleared when switching modes |
| Android server address | PASS | 83 Java checks cover the reported hidden-space error, Unicode clipboard boundaries, malformed URLs, loopback/unspecified addresses, ports, valid private HTTP and hosted HTTPS |
| Pairing address shown on the web | PASS | Localhost address is not offered for copying to a physical phone; a hosted HTTPS address remains copyable |
| Sign in from another device | PASS | Separate browser cookie jar signs in after the original signs out, receives the paired phone's fix and its next movement; simulated clients, not physical phones |
| Concurrent location ordering | PASS | Forced two requests to read the same old row, then made the older report commit last; the newer location survives |
| Real street map | PASS | Firefox loaded visible 256 px OpenStreetMap street tiles; no placeholder map or application demo mode |
| Moving location | PASS | Two reports moved the existing marker and updated coordinates |
| Accuracy circle | PASS | Map overlay and reported accuracy displayed |
| Zoom and panning | PASS | Zoom in/out, pointer dragging, and Follow phone tested in Firefox |
| Polling during map use | PASS | The map and its card remain attached; tile nodes and zoom are retained across updates |
| Mobile layout | PASS | Pin remains centered after viewport resize; no horizontal page overflow |
| Distance from the viewer | PASS | Known zero/one-degree/date-line distances; meters/km; updates after either device moves |
| Viewer location handling | PASS | Permission denial, stale viewer fix, stop/clear, no browser storage and no viewer-location POSTs |
| Directions and travel time link | PASS | Google Maps directions URL uses the latest destination and fresh viewer origin; stale/future/denied/stopped viewer origins omitted, canceled watch ignored, freshness rechecked on activation after a hidden-tab delay, no automatic external routing request |
| Old/stopped location | PASS | Old fixes and stopped sharing are labeled; no old point is presented as a fresh fix |
| Backend outage | PASS | Actual test server stopped; browser retained the last location with a warning and recovered after restart |
| Concurrent traffic | PASS | 200 requests from 12 concurrent clients, zero HTTP errors with DELETE journaling; local p95 response time 31.3 ms |
| Unexpected process stop | PASS | Production server forcibly killed and restarted; accounts, sessions, phone credentials and committed locations survived |
| Existing database upgrade | PASS | Legacy WAL database reopened with DELETE journaling; integrity, original account/session, paired token and location survive; login and new reports still work |
| Database backup/restore | PASS | Live SQLite backup, integrity check, private permissions, overwrite refusal and restored reporting credentials verified |
| Production serving | PASS | Waitress served the API, map assets and APK; secure cookies, HEAD, health, private access and revocation checked |
| Android package | PASS | APK 1.0.1/versionCode 2 compiled against API 35; archive integrity, v2/v3 signatures and downloaded APK bytes verified; Android 8.0+ manifest checked |
| Upload package for nahabi | PASS | 37 source/configuration/asset files including the signed APK; no private data or keys; exact account configuration exercised through a fresh WSGI process using temporary paths |

The concurrent-traffic result measures the backend on this computer. It is a small burst test, not a large-scale load test, endurance test, mobile network benchmark or hosting uptime measurement.

The free-hosting guide targets a small PythonAnywhere project. SQLite now uses DELETE rollback journaling instead of WAL for network-filesystem compatibility. Local checks do not verify PythonAnywhere's actual storage locks, speed, expiry renewal or deployment; these remain real-host checks. The guide describes these limits and does not claim a deployed site or guaranteed recovery.

The prepared `deploy/phonelink-nahabi.zip` extracts to `phone-link-main/` and includes the account-specific WSGI configuration and APK. Its extracted files were checked against the source; health, unknown-account rejection, sign-in, Secure cookies, origin checks, pairing, location reports, map assets, APK download, private-path denial and revocation passed using an isolated temporary database. The actual host was only read: on 19 October 2026, `https://nahabi.pythonanywhere.com/` and `/api/health` returned the provider's Coming Soon page with HTTP 404. Uploading the package and configuring/reloading the Web app are still required in the signed-in hosting account.

## Issues found and fixed

Five-second polling was replacing the map's surrounding card. In Firefox this interrupted pending street tiles during zoom. The dashboard now reuses both the card and map in place. The browser test checks their identity, actual street tile loading, zoom, following and mobile centering. The full browser flow passed after this fix.

Concurrent reports could both read an old timestamp and let the older report overwrite a newer fix. The database UPDATE now compares timestamps atomically. A regression test uses a barrier and an event to force the problematic order without timing sleeps; it fails against the old implementation and passes with the fix.

Pasting a nonbreaking space after `http://` reproduced the reported Java “Illegal character in authority at index 7” error. The APK now trims surrounding Unicode clipboard spaces, rejects internal spaces and malformed origins with clear messages, and explains why localhost/loopback cannot point to a PC from a physical phone. No hostname DNS lookup is used during address validation. The dashboard also prevents copying its own localhost address as a phone server address. The rebuilt APK is signed with the existing development key for an in-place update; real-device installation remains unverified.

## Test data and real data

API, browser and hosting tests use separate temporary databases. Synthetic coordinates are sent through the real report API to exercise movement; they are not actual phone GPS readings. Viewer permission/location cases use controlled browser callbacks to exercise calculations and error handling; a real viewer GPS fix remains a device test. No synthetic coordinates are inserted into your dashboard's database. The application has no demo data mode: a phone must report a fix before a map appears.

Street tiles are real OpenStreetMap data. Tile availability and detail depend on that external service and the viewer's internet connection. Account credentials and reporting tokens are not sent to the tile provider.

Road distance and estimated travel time are shown **in Google Maps**, opened through its documented keyless directions URLs. The dashboard calculates straight-line distance only. Link construction, updates and privacy behavior were tested; an actual Google Maps route calculation/navigation on a physical viewing phone was not. Opening directions sends destination and any fresh viewer origin to Google; the dashboard makes no background routing requests. Reopen directions if the phone moves.

## Not yet verified

- A physical Android installation, runtime permissions and an outdoor GPS fix.
- The viewing device's real browser location permission and accuracy over HTTPS. Distance is a straight-line estimate; it is not route length.
- Opening Google Maps directions on a physical phone, including local route availability and travel time for its chosen transport mode.
- Accurate movement while carrying a real phone, with the screen locked for at least 10 minutes.
- Actual Android battery restrictions, phone internet loss/recovery, notification Stop, force-stop and reboot behavior.
- A real public host's HTTPS certificate, persistent disk, automatic restart, backups and limits.
- Reports from mobile data after the phone leaves the computer's Wi-Fi, viewed from a second phone.
- Long-duration battery usage, host uptime, or behavior under large traffic volumes.

The code and tests do not support locating an unprepared phone by IMEI. Location must come from the paired APK. The current local server is not reachable by a lost phone outside the local network until public hosting is configured.

## Reproduce

```bash
python3 -m unittest discover -s tests -v
python3 tests/android_address_smoke.py
python3 tests/browser_smoke.py
python3 android/build.py
python3 -m pip install -r requirements-deploy.txt
python3 tests/hosting_smoke.py
```

The browser test requires Firefox and geckodriver. The Android build requires Java 21 and downloads official SDK tools on its first run. Browser screenshots in `dist/` show synthetic test locations; the real dashboard waits for the paired APK.

APK: `dist/phonelink.apk`, version **1.0.1** (versionCode **2**), 29,222 bytes.

SHA-256: `59e32a66642004dd6a45bf9dabf7e6cc465d80004c084390c727b495a856d33b`.
