#!/usr/bin/env python3
"""Package tracked PhoneLink source and the built APK for nahabi's free WSGI host."""
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist/phonelink-nahabi.zip"
PUBLISHED = "deploy/phonelink-nahabi.zip"


def main():
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    paths = sorted({path for path in tracked if path and path != PUBLISHED})
    paths.append("dist/phonelink.apk")
    required = {"server.py", "wsgi.py", "web/index.html", "deploy/pythonanywhere_nahabi_wsgi.py", "deploy/NAHABI_SETUP.md"}
    if not required.issubset(paths):
        raise SystemExit("Stage the source and hosting configuration with Git before packaging.")
    for name in paths:
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or any(part in {".git", ".tools", ".venv", "data", "__pycache__"} for part in relative.parts):
            raise SystemExit("Refusing to package a private or invalid path.")
        if relative.suffix.lower() in {".db", ".sqlite3", ".jks", ".keystore", ".pem", ".p12", ".pfx", ".zip"} or relative.name.startswith(".env"):
            raise SystemExit("Refusing to package a database, secret or nested archive.")
        target = ROOT / name
        if target.is_symlink() or not target.is_file():
            raise SystemExit("All package inputs must be regular files. Build the APK first.")
    OUTPUT.parent.mkdir(exist_ok=True)
    temporary = OUTPUT.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in paths:
                info = zipfile.ZipInfo("phone-link-main/" + name)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, (ROOT / name).read_bytes())
        temporary.replace(OUTPUT)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Upload package: {OUTPUT} ({OUTPUT.stat().st_size:,} bytes, {len(paths)} files)")


if __name__ == "__main__":
    main()
