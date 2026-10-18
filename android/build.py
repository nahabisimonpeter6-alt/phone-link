#!/usr/bin/env python3
"""Build the APK using official Android SDK tools, Java 21 and Python 3. No Gradle."""
import hashlib
import concurrent.futures
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / ".tools/android-sdk"
BUILD = ROOT / "android/build"
PACKAGES = [
    ("platform-35_r02.zip", "0bb560a90a7a2cbd0dd8348224d518b638fe7949", 64273788, "android-35", "platforms/android-35"),
    ("build-tools_r35_linux.zip", "2cfaa0bbb2336e9ec18ed3ecea84fa2e2af607bc", 61958799, "android-15", "build-tools/35.0.0"),
]


def run(*args):
    subprocess.run([str(a) for a in args], check=True, cwd=ROOT)


def download(filename, size, archive):
    """Resumable ranged download; parallel connections help on slow SDK mirrors."""
    parts = SDK / (filename + ".parts")
    parts.mkdir(exist_ok=True)
    chunk = 4 * 1024 * 1024
    count = (size + chunk - 1) // chunk

    def fetch(index):
        start, end = index * chunk, min(size, (index + 1) * chunk) - 1
        target = parts / str(index)
        if target.exists() and target.stat().st_size == end - start + 1:
            return target
        for attempt in range(3):
            try:
                saved = target.stat().st_size if target.exists() else 0
                if saved > end - start + 1:
                    target.unlink(); saved = 0
                resume = start + saved
                request = urllib.request.Request("https://dl.google.com/android/repository/" + filename,
                    headers={"Range": f"bytes={resume}-{end}"})
                with urllib.request.urlopen(request, timeout=90) as response, target.open("ab") as out:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {resume}-{end}/{size}":
                        raise RuntimeError("Unexpected SDK range response")
                    shutil.copyfileobj(response, out)
                if target.stat().st_size != end - start + 1:
                    raise RuntimeError("Incomplete SDK download")
                print(f"  {filename}: part {index + 1}/{count}", flush=True)
                return target
            except Exception:
                if attempt == 2: raise
                time.sleep(1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        ordered = list(pool.map(fetch, range(count)))
    with archive.open("wb") as out:
        for part in ordered:
            with part.open("rb") as source: shutil.copyfileobj(source, out)
    shutil.rmtree(parts)


def prepare_sdk():
    SDK.mkdir(parents=True, exist_ok=True)
    for filename, checksum, size, folder, destination in PACKAGES:
        target = SDK / destination
        if target.exists():
            continue
        archive = SDK / filename
        if not archive.exists() or archive.stat().st_size != size:
            print("Downloading official Android SDK package:", filename, flush=True)
            download(filename, size, archive)
        if hashlib.sha1(archive.read_bytes()).hexdigest() != checksum:
            archive.unlink()
            raise RuntimeError("SDK checksum mismatch. Run again to re-download.")
        staging = SDK / ("extract-" + filename)
        staging.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as package:
            package.extractall(staging)
            # zipfile does not preserve Unix executable permissions.
            for entry in package.infolist():
                mode = entry.external_attr >> 16
                if mode and not entry.is_dir():
                    (staging / entry.filename).chmod(mode & 0o777)
        source = staging / folder
        if not source.exists():
            candidates = list(staging.iterdir())
            if len(candidates) != 1: raise RuntimeError("Unexpected Android SDK archive layout")
            source = candidates[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        shutil.rmtree(staging)
        archive.unlink()


def main():
    for command in ("java", "javac", "keytool"):
        if not shutil.which(command): raise SystemExit("Install OpenJDK 21 first. Missing: " + command)
    prepare_sdk()
    tools = SDK / "build-tools/35.0.0"
    android_jar = SDK / "platforms/android-35/android.jar"
    if BUILD.exists(): shutil.rmtree(BUILD)
    for folder in ("gen", "classes", "dex"):
        (BUILD / folder).mkdir(parents=True)
    run(tools / "aapt2", "compile", "--dir", ROOT / "android/res", "-o", BUILD / "resources.zip")
    run(tools / "aapt2", "link", "-o", BUILD / "base.apk", "-I", android_jar,
        "--manifest", ROOT / "android/AndroidManifest.xml", "--java", BUILD / "gen", BUILD / "resources.zip")
    sources = list((ROOT / "android/src").rglob("*.java")) + list((BUILD / "gen").rglob("*.java"))
    run("javac", "--release", "8", "-encoding", "UTF-8", "-classpath", android_jar, "-d", BUILD / "classes", *sources)
    run(tools / "d8", "--min-api", "26", "--lib", android_jar, "--output", BUILD / "dex", *list((BUILD / "classes").rglob("*.class")))
    with zipfile.ZipFile(BUILD / "base.apk", "a", zipfile.ZIP_DEFLATED) as package:
        package.write(BUILD / "dex/classes.dex", "classes.dex")
    run(tools / "zipalign", "-f", "4", BUILD / "base.apk", BUILD / "aligned.apk")
    key = ROOT / ".tools/phonelink-development.jks"
    if not key.exists():
        run("keytool", "-genkeypair", "-keystore", key, "-storepass", "android", "-keypass", "android", "-alias", "phonelink",
            "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000", "-dname", "CN=PhoneLink Development")
        key.chmod(0o600)
    output = ROOT / "dist/phonelink.apk"
    output.parent.mkdir(exist_ok=True)
    run(tools / "apksigner", "sign", "--ks", key, "--ks-key-alias", "phonelink", "--ks-pass", "pass:android", "--key-pass", "pass:android", "--out", output, BUILD / "aligned.apk")
    run(tools / "apksigner", "verify", "--verbose", output)
    print("\nAPK ready:", output, f"({output.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
