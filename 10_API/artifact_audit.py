#!/usr/bin/env python3
"""Read-only availability audit for historical Engine run artifacts."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def connect_read_only(database: Path) -> sqlite3.Connection:
    uri = f"{database.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def audit_artifacts(database: Path) -> list[dict[str, Any]]:
    observed_at = datetime.now(UTC).isoformat()
    records = []
    with connect_read_only(database) as connection:
        rows = connection.execute(
            "SELECT id,engine,run_at,stdout_path,stderr_path "
            "FROM engine_runs ORDER BY id"
        )
        for run_id, engine, run_at, stdout_path, stderr_path in rows:
            for stream, raw_path in (
                ("stdout", stdout_path),
                ("stderr", stderr_path),
            ):
                path = Path(raw_path) if raw_path else None
                availability = (
                    "not_recorded"
                    if path is None
                    else "available"
                    if path.is_file()
                    else "unavailable"
                )
                records.append(
                    {
                        "run_id": int(run_id),
                        "engine": str(engine),
                        "run_at": str(run_at),
                        "stream": stream,
                        "path": str(path) if path is not None else None,
                        "availability": availability,
                        "observed_at": observed_at,
                    }
                )
    return records


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path.home() / ".gmv_core" / "09_DATABASE" / "GMV.db",
    )
    parser.add_argument("--json", action="store_true")
    options = parser.parse_args(arguments)
    try:
        records = audit_artifacts(options.database)
    except (OSError, sqlite3.Error) as error:
        print(f"error: artifact audit failed: {error}", file=sys.stderr)
        return 2

    if options.json:
        print(json.dumps(records, sort_keys=True))
    else:
        for record in records:
            print(
                "|".join(
                    (
                        str(record["run_id"]),
                        str(record["engine"]),
                        str(record["stream"]),
                        str(record["availability"]),
                        str(record["path"] or ""),
                    )
                )
            )
    return 1 if any(r["availability"] == "unavailable" for r in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
