# PhoneLink verification report

**Result:** The tested web map, API, production server and recovery scenarios pass. This is ready for a real-device pilot, not a guarantee of uninterrupted lost-phone recovery. A physical Android test and a public HTTPS deployment test remain.

## Verified results

| Area | Result | Evidence |
| --- | --- | --- |
| API and access controls | PASS | 18 integration tests against real HTTP and SQLite |
| Real street map | PASS | Firefox loaded visible 256 px OpenStreetMap street tiles; no placeholder map or application demo mode |
| Moving location | PASS | Two reports moved the existing marker and updated coordinates |
| Accuracy circle | PASS | Map overlay and reported accuracy displayed |
| Zoom and panning | PASS | Zoom in/out, pointer dragging, and Follow phone tested in Firefox |
| Polling during map use | PASS | The map and its card remain attached; tile nodes and zoom are retained across updates |
| Mobile layout | PASS | Pin remains centered after viewport resize; no horizontal page overflow |
| Distance from the viewer | PASS | Known zero/one-degree/date-line distances; meters/km; updates after either device moves |
| Viewer location handling | PASS | Permission denial, stale viewer fix, stop/clear, no browser storage and no viewer-location POSTs |
| Old/stopped location | PASS | Old fixes and stopped sharing are labeled; no old point is presented as a fresh fix |
| Backend outage | PASS | Actual test server stopped; browser retained the last location with a warning and recovered after restart |
| Concurrent traffic | PASS | 200 requests from 12 concurrent clients, zero HTTP errors; local p95 response time 43.4 ms |
| Unexpected process stop | PASS | Production server forcibly killed and restarted; accounts, sessions, phone credentials and committed locations survived |
| Database backup/restore | PASS | Live SQLite backup, integrity check, private permissions, overwrite refusal and restored reporting credentials verified |
| Production serving | PASS | Waitress served the API, map assets and APK; secure cookies, HEAD, health, private access and revocation checked |
| Android package | PASS | Java compiled against API 35; APK archive integrity and v2/v3 signatures verified; Android 8.0+ manifest checked |

The concurrent-traffic result measures the backend on this computer. It is a small burst test, not a large-scale load test, endurance test, mobile network benchmark or hosting uptime measurement.

## Issue found and fixed

Five-second polling was replacing the map's surrounding card. In Firefox this interrupted pending street tiles during zoom. The dashboard now reuses both the card and map in place. The browser test checks their identity, actual street tile loading, zoom, following and mobile centering. The full browser flow passed after this fix.

## Test data and real data

API, browser and hosting tests use separate temporary databases. Synthetic coordinates are sent through the real report API to exercise movement; they are not actual phone GPS readings. Viewer permission/location cases use controlled browser callbacks to exercise calculations and error handling; a real viewer GPS fix remains a device test. No synthetic coordinates are inserted into your dashboard's database. The application has no demo data mode: a phone must report a fix before a map appears.

Street tiles are real OpenStreetMap data. Tile availability and detail depend on that external service and the viewer's internet connection. Account credentials and reporting tokens are not sent to the tile provider.

## Not yet verified

- A physical Android installation, runtime permissions and an outdoor GPS fix.
- The viewing device's real browser location permission and accuracy over HTTPS. Distance is a straight-line estimate; it is not route length.
- Accurate movement while carrying a real phone, with the screen locked for at least 10 minutes.
- Actual Android battery restrictions, phone internet loss/recovery, notification Stop, force-stop and reboot behavior.
- A real public host's HTTPS certificate, persistent disk, automatic restart, backups and limits.
- Reports from mobile data after the phone leaves the computer's Wi-Fi, viewed from a second phone.
- Long-duration battery usage, host uptime, or behavior under large traffic volumes.

The code and tests do not support locating an unprepared phone by IMEI. Location must come from the paired APK. The current local server is not reachable by a lost phone outside the local network until public hosting is configured.

## Reproduce

```bash
python3 -m unittest discover -s tests -v
python3 tests/browser_smoke.py
python3 -m pip install -r requirements-deploy.txt
python3 tests/hosting_smoke.py
python3 android/build.py
```

The browser test requires Firefox and geckodriver. The Android build requires Java 21 and downloads official SDK tools on its first run. Browser screenshots in `dist/` show synthetic test locations; the real dashboard waits for the paired APK.

APK: `dist/phonelink.apk`, 25,126 bytes.

SHA-256: `5f556481f14a618fa87a6bac6e5e8154939bf83a8d056d10a06a9d6b98fcff4d`.
