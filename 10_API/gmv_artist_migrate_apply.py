#!/usr/bin/env python3
"""Apply one reviewed GMV artist migration plan without reclassification."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
from typing import Callable

from gmv_artist_migrate_common import (
    MigrationError,
    SCHEMA_VERSION,
    atomic_text_write,
    contained,
    json_write,
    load_plan,
    normalized_relative,
    require_plain_directory,
    sha256_file,
)


def copy_directory_tree(template: Path, destination: Path) -> None:
    for current, directory_names, file_names in os.walk(template, topdown=True, followlinks=False):
        current_path = Path(current)
        if current_path.is_symlink():
            raise MigrationError(f"template contains symlink directory: {current_path}")
        for name in directory_names + file_names:
            if (current_path / name).is_symlink():
                raise MigrationError(f"template contains symlink: {current_path / name}")
        relative = current_path.relative_to(template)
        (destination / relative).mkdir(exist_ok=False if relative == Path(".") else True)


def result_markdown(result: dict) -> str:
    lines = [
        f"# GMV Artist Migration Result — {result['artist']}",
        "",
        f"Status: **{result['status']}**",
        "",
        f"- Plan: `{result['plan_path']}`",
        f"- Plan SHA-256: `{result['plan_sha256']}`",
        f"- Source: `{result['source_root']}`",
        f"- Destination: `{result['destination_root']}`",
        f"- Planned: {result['planned_item_count']}; moved: {result['moved_item_count']}; failed: {result['failed_item_count']}",
        "",
        "## Item ledger",
        "",
        "| ID | Source | Destination | Status |",
        "|---|---|---|---|",
    ]
    for item in result["items"]:
        lines.append(f"| {item['id']} | `{item['source']}` | `{item['destination']}` | {item['status']} |")
    lines.append("")
    return "\n".join(lines)


def preflight(plan: dict) -> tuple[Path, Path, Path, list[tuple[dict, Path, Path]]]:
    paths = plan["paths"]
    source_root = require_plain_directory(Path(paths["source_root"]), "source root")
    template_root = require_plain_directory(Path(paths["template_root"]), "template root")
    destination_root = require_plain_directory(Path(paths["destination_root"]), "destination root")
    destination_artist = Path(paths["destination_artist_root"])
    if destination_artist.parent.resolve() != destination_root.resolve() or destination_artist.name != plan["artist"]["destination_name"]:
        raise MigrationError("destination artist root is inconsistent with destination root or artist")
    contained(destination_root, destination_artist, "destination artist root")
    if destination_artist.exists() or destination_artist.is_symlink():
        raise MigrationError(f"destination artist root already exists: {destination_artist}")
    moves = []
    for item in plan["items"]:
        source = contained(source_root, source_root / normalized_relative(item["source_relpath"], f"item {item['id']} source"), "source")
        destination = contained(destination_artist, destination_artist / normalized_relative(item["destination_relpath"], f"item {item['id']} destination"), "destination")
        if source.is_symlink() or not source.is_file():
            raise MigrationError(f"source is missing, not a regular file, or a symlink: {source}")
        if destination.exists() or destination.is_symlink():
            raise MigrationError(f"destination already exists: {destination}")
        moves.append((item, source, destination))
    return source_root, template_root, destination_artist, moves


def apply_plan(
    plan_path: Path,
    input_fn: Callable[[str], str] = input,
    result_base: Path | None = None,
) -> dict:
    plan = load_plan(plan_path)
    source_root, template_root, destination_artist, moves = preflight(plan)
    summary = plan["summary"]
    prompt = (
        "GMV ARTIST MIGRATION\n"
        f"Artist: {plan['artist']['destination_name']}\n"
        f"Source files: {summary['source_files']}\n"
        f"Canonical moves: {summary['canonical_moves']}\n"
        f"TEMP_IMPORT moves: {summary['temp_import_moves']}\n"
        f"Destination: {destination_artist}\n\nProceed? [y/N] "
    )
    if input_fn(prompt).strip().lower() != "y":
        raise MigrationError("migration cancelled; no filesystem changes were made")
    result_items = [{"id": item["id"], "source": str(source), "destination": str(destination), "status": "PENDING"} for item, source, destination in moves]
    result = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artist": plan["artist"]["destination_name"],
        "source_root": str(source_root),
        "destination_root": str(destination_artist),
        "plan_path": str(plan_path.resolve()),
        "plan_sha256": sha256_file(plan_path),
        "template_path": str(template_root),
        "planned_item_count": len(moves),
        "moved_item_count": 0,
        "failed_item_count": 0,
        "items": result_items,
        "status": "FAILED",
    }
    try:
        copy_directory_tree(template_root, destination_artist)
        for index, (_item, source, destination) in enumerate(moves):
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise MigrationError(f"destination appeared during apply: {destination}")
            shutil.move(str(source), str(destination))
            result_items[index]["status"] = "MOVED"
            result["moved_item_count"] += 1
        result["status"] = "COMPLETED"
    except Exception as exc:
        result["failed_item_count"] = len(moves) - result["moved_item_count"]
        result["error"] = str(exc)
        result["status"] = "PARTIAL" if result["moved_item_count"] else "FAILED"
    finally:
        default_base = plan_path.resolve().with_name(
            f"{plan['artist']['destination_name']}_MIGRATION_RESULT"
        )
        ledger_base = (result_base or default_base).expanduser().resolve()
        json_write(ledger_base.with_suffix(".json"), result)
        atomic_text_write(ledger_base.with_suffix(".md"), result_markdown(result))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument(
        "--result-output",
        type=Path,
        help="ledger base path without extension; does not bypass confirmation",
    )
    args = parser.parse_args(argv)
    try:
        result = apply_plan(args.plan, result_base=args.result_output)
    except (MigrationError, OSError) as exc:
        parser.error(str(exc))
    print(f"{result['status']}: {result['moved_item_count']}/{result['planned_item_count']} moved")
    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
