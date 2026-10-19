# Free hosting for a small PhoneLink project

PhoneLink needs an online Python backend and a private, persistent database. You can use it with your PC switched off after moving those to a host. A map API key and a static website alone cannot run the tracker.

## The simple free option

[PythonAnywhere's free account](https://www.pythonanywhere.com/pricing/) provides one Python web app and 512 MiB of private storage. Its supplied `yourname.pythonanywhere.com` address includes [HTTPS](https://help.pythonanywhere.com/pages/HTTPSSetup/). There is no domain purchase or map API key required. Choose the free account, not a paid plan.

**Renew the web app before its monthly expiry.** The current free plan has [one web worker and a one-month expiry](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/); see the provider's [renewal explanation](https://blog.pythonanywhere.com/129/). Receiving phone reports does not replace renewing the web app. If it expires, tracking reports cannot be received until re-enabled. There is no promise of uninterrupted uptime.

This is suitable for trying a small personal project. PythonAnywhere offers SQLite but [does not recommend it for production](https://help.pythonanywhere.com/pages/KindsOfDatabases/). Its network filesystem can have locking problems. PhoneLink now uses DELETE rollback journaling instead of WAL, since [SQLite WAL does not support network filesystems](https://www.sqlite.org/wal.html). That removes a definite incompatibility but cannot guarantee the host's file locking or durable recovery. Keep the single free worker, test real reporting on the host, and keep private backups. For dependable recovery, use a host with durable local storage or adapt the backend to a managed database. A new free PythonAnywhere account does not include MySQL.

## Put the project online

For the account **nahabi**, use the prepared [account-specific instructions](deploy/NAHABI_SETUP.md) and [WSGI configuration](deploy/pythonanywhere_nahabi_wsgi.py). The downloadable `deploy/phonelink-nahabi.zip` also includes the APK, so it can be uploaded as one package.

1. Create your free account at PythonAnywhere. Note the exact HTTPS website address shown on its **Web** page. EU accounts use the EU domain shown there.
2. While signed into GitHub as the repository owner, open [phone-link](https://github.com/nahabisimonpeter6-alt/phone-link), choose **Code → Download ZIP**, and upload the ZIP with PythonAnywhere's **Files** page. The repository is private; do not make it public or paste GitHub credentials into a command.
3. Open a PythonAnywhere Bash console and extract the ZIP in your home directory. For the usual downloaded filename:

   ```bash
   python3 -m zipfile -e phone-link-main.zip .
   ```

   The project should now be `/home/YOUR_USERNAME/phone-link-main`. Check the actual folder name in Files.
4. Build the APK on your build computer using `python3 android/build.py`. In PythonAnywhere's Files page, create `phone-link-main/dist` and upload **only** `dist/phonelink.apk` into it. Keep signing keys private on your build computer. The Android SDK/build output is too large for this small hosting plan; you only need the finished APK on the host.
5. On **Web**, choose **Add a new web app → Manual configuration**, then a Python version **3.10 or newer**. This WSGI application uses the standard library; no framework, virtual environment or Waitress installation is required for this setup.
6. Open the **WSGI configuration file** linked on the Web page. Replace its sample contents with the following, changing all `YOUR_USERNAME` values and using the exact HTTPS address from step 1:

   ```python
   import os
   import sys

   project = "/home/YOUR_USERNAME/phone-link-main"
   sys.path.insert(0, project)
   os.environ["PHONELINK_PUBLIC_URL"] = "https://YOUR_USERNAME.pythonanywhere.com"
   os.environ["PHONELINK_DB"] = "/home/YOUR_USERNAME/phonelink-private/phonelink.sqlite3"

   from wsgi import application
   ```

   PhoneLink creates the private database directory on first use. A new database starts with no accounts; create your account on the hosted site. Do not upload the whole `data/` or `.tools/` directory.
7. Enable [Force HTTPS](https://help.pythonanywhere.com/pages/ForcingHTTPS/) on Web, then **Reload** the app. Leave PythonAnywhere's static-file mapping table empty; PhoneLink serves only its allowed assets. Never map your home folder or database directory to a public URL. You do not run `server.py` in a console: PythonAnywhere runs `wsgi.application` for you.
8. Open `https://YOUR_WEBSITE/api/health` and check it shows `{"ok": true}`. Open the homepage, create an account, and download the APK through the website. Pair the phone using the new **HTTPS** address and a new code, then start sharing. A phone paired to your PC's old address must be re-paired to this host.

In the APK, paste only that website address. Do not enter `localhost:8080`: on a physical phone that points to the phone, not to PythonAnywhere or your PC. Open the exact HTTPS address in the phone's browser to check it before pairing. If installing APK 1.0.1 to fix address validation, upload the new APK to the host's `dist/` folder too; updating the source ZIP alone does not replace the binary.

## Check before relying on it

With the computer switched off, view the hosted site from another phone. Sign in, tap **Show my distance**, allow browser location access and confirm new phone reports move the marker. Test the tracked phone over mobile data, screen locked, and after temporary network loss. Open **Route & travel time in Google Maps** for route distance and estimated travel time. Directions capture the latest received destination; reopen them if the phone moves.

The hosting provider's Files page and application are separate accounts: your PythonAnywhere login manages hosting, while your PhoneLink login protects your device locations. Keep both passwords safe. Download a private database backup regularly. On this shared/network-storage setup, disable the web app before running a backup or migration so only one process accesses the database. Then run (with your username):

```bash
python3 /home/YOUR_USERNAME/phone-link-main/backup.py --db /home/YOUR_USERNAME/phonelink-private/phonelink.sqlite3
```

Download the printed backup path through Files and keep it private off the host. Re-enable the web app and test reporting afterward. Do not overwrite an existing database during a code update.

This setup has not been deployed or verified in a real PythonAnywhere account by these local tests. Check the Web error log if startup fails. Hosting expiry, storage limits, database locks or phone connectivity can interrupt tracking. Render's free web service is not an unchanged substitute for this SQLite app: its [filesystem is ephemeral and free services have no persistent disk](https://render.com/docs/free), so accounts and pairings could be lost on restart.
