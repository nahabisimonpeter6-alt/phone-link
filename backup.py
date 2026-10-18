#!/usr/bin/env python3
"""Make a consistent, private backup of a live PhoneLink SQLite database."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile

from server import ROOT


def backup_database(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError("The source database does not exist.")
    if destination.exists():
        raise ValueError("The backup already exists. Choose a new filename.")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".phonelink-backup-", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(temporary)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
            original.execute("SELECT 1 FROM devices LIMIT 1")
            with closing(sqlite3.connect(temporary)) as copy:
                original.backup(copy)
                if copy.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed.")
        temporary.chmod(0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("PHONELINK_DB", str(ROOT / "data/phonelink.sqlite3")))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    parser.add_argument("--output", default=str(ROOT / "data/backups" / f"phonelink-{stamp}.sqlite3"))
    args = parser.parse_args()
    try:
        print("Verified backup:", backup_database(args.db, args.output))
    except (ValueError, sqlite3.Error, OSError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
