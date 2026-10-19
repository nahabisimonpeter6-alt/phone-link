#!/usr/bin/env python3
"""Run Android pairing-address validation on Java 8-compatible bytecode; no SDK/network needed."""
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    for command in ("javac", "java"):
        if not shutil.which(command):
            raise SystemExit("Install OpenJDK 21 first. Missing: " + command)
    with tempfile.TemporaryDirectory(prefix="phonelink-address-") as output:
        subprocess.run([
            "javac", "--release", "8", "-encoding", "UTF-8", "-d", output,
            str(ROOT / "android/src/app/phonelink/tracker/ServerAddress.java"),
            str(ROOT / "tests/java/app/phonelink/tracker/ServerAddressSmoke.java"),
        ], check=True)
        subprocess.run(["java", "-ea", "-cp", output, "app.phonelink.tracker.ServerAddressSmoke"], check=True)


if __name__ == "__main__":
    main()
