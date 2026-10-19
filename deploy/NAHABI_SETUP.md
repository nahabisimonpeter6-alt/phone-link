# Put PhoneLink online as nahabi

Your expected US website address is **https://nahabi.pythonanywhere.com**. If the Web tab shows an EU address, use that exact address and change `PUBLIC_URL` in the supplied WSGI configuration.

[Download phonelink-nahabi.zip](https://github.com/nahabisimonpeter6-alt/phone-link/raw/refs/heads/main/deploy/phonelink-nahabi.zip) while signed into GitHub as the repository owner. It contains the source, street-map assets, signed APK 1.0.1 and your hosting configuration. It contains no accounts, saved locations, signing keys or SDK. Your PC can be switched off after deployment.

1. Sign in at **https://www.pythonanywhere.com** with username **nahabi**. In **Web**, choose **Add a new web app → Manual configuration**, then Python **3.10 or newer**. If a web app is already listed for this address, use that entry. No Flask, virtualenv, pip install or console server is needed.
2. In **Files**, upload **phonelink-nahabi.zip** to `/home/nahabi`.
3. Open a **Bash console** and extract it:

   ```bash
   cd /home/nahabi
   python3 -m zipfile -e phonelink-nahabi.zip .
   ```

   This creates `/home/nahabi/phone-link-main`. On an update it replaces application files only; the database is outside this folder.
4. In **Web**, open the **WSGI configuration file** link. Replace its sample contents with the contents of `/home/nahabi/phone-link-main/deploy/pythonanywhere_nahabi_wsgi.py`, then **Save**. Do not replace the project's own `wsgi.py`.
5. Leave **Static files** mappings empty. Enable **Force HTTPS** and click **Reload**. Do not map the home folder or private database folder to a web URL.
6. Open **https://nahabi.pythonanywhere.com/api/health**. It must show `{"ok": true}`. The homepage must show PhoneLink, not the provider's default page. If either fails, open the error log linked on the Web tab to diagnose it.
7. Create a **PhoneLink** account on that website. This is separate from your hosting login. Download the APK at **https://nahabi.pythonanywhere.com/download/phonelink.apk**. Create a fresh pairing code and enter **https://nahabi.pythonanywhere.com** as the APK's server address.

Keep the single free worker and renew the free web app before its one-month expiry. Read [FREE_HOSTING.md](../FREE_HOSTING.md) for the host's storage limits, SQLite caveats, and private backup steps. The package is checked locally; the actual hosted site must pass the health, sign-in and real-phone reporting checks after upload. Never upload an existing database or signing key with application files.

To rebuild the upload package after changing source, stage the source files with Git and run `python3 deploy/package_pythonanywhere.py` after building the APK. It creates `dist/phonelink-nahabi.zip`; copy that file to `deploy/phonelink-nahabi.zip` when updating the downloadable repository copy. Existing ZIPs are excluded from the package.
