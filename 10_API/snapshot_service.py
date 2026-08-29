#!/usr/bin/env python3
import importlib
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

database_module = importlib.import_module("gmv_core.database")

CORE = Path.home() / ".gmv_core"
DB = CORE / "09_DATABASE/GMV.db"
SNAPSHOT_DIR = CORE / "05_OUTPUT/snapshots"


def next_snapshot_path():
    timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    path = SNAPSHOT_DIR / f"GMV_CORE_{timestamp}.sql"
    sequence = 1
    while path.exists():
        path = SNAPSHOT_DIR / f"GMV_CORE_{timestamp}_{sequence:02d}.sql"
        sequence += 1
    return path


def create_snapshot():
    if not DB.is_file():
        raise FileNotFoundError(f"Database not found: {DB}")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = next_snapshot_path()

    with database_module.connect_path(DB) as conn, path.open("x", encoding="utf-8") as dump:
        for statement in conn.iterdump():
            dump.write(f"{statement}\n")

    return path


def list_snapshots():
    if not SNAPSHOT_DIR.is_dir():
        return []
    return sorted(SNAPSHOT_DIR.glob("GMV_CORE_*.sql"), reverse=True)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  snapshot_service.py create")
        print("  snapshot_service.py list")
        sys.exit(2)

    command = sys.argv[1]
    if command == "create":
        try:
            print(create_snapshot())
        except (OSError, sqlite3.Error) as error:
            print(f"Snapshot failed: {error}")
            sys.exit(1)
    elif command == "list":
        for path in list_snapshots():
            print(path)
    else:
        print("Unknown command:", command)
        sys.exit(2)


if __name__ == "__main__":
    main()
