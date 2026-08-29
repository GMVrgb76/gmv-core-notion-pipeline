#!/usr/bin/env python3
"""Shared safety primitives for the deterministic GMV artist migrator."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

SCHEMA_VERSION = "gmv.artist-migration-plan.v0.1"
TEMP_IMPORT = "09_TEMP_IMPORT"


class MigrationError(ValueError):
    """A plan or filesystem condition violates the migration contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def yaml_write(path: Path, value: dict[str, Any]) -> None:
    atomic_text_write(path, yaml.safe_dump(value, allow_unicode=True, sort_keys=False))


def json_write(path: Path, value: dict[str, Any]) -> None:
    atomic_text_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def normalized_relative(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise MigrationError(f"{label} must be a non-empty relative path")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise MigrationError(f"{label} escapes its declared root: {value!r}")
    # Backslashes are valid macOS filename characters, but accepting them would
    # make plans ambiguous when read on another platform.
    if "\\" in value:
        raise MigrationError(f"{label} must use POSIX separators only: {value!r}")
    return Path(*candidate.parts)


def contained(root: Path, candidate: Path, label: str) -> Path:
    resolved_root = root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise MigrationError(f"{label} escapes declared root: {candidate}") from exc
    return resolved_candidate


def require_plain_directory(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise MigrationError(
            f"{label} must be an existing non-symlink directory: {path}"
        )
    return path.resolve()


def load_plan(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise MigrationError(f"plan must be an existing non-symlink file: {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MigrationError(f"invalid YAML plan: {exc}") from exc
    if not isinstance(loaded, dict):
        raise MigrationError("plan root must be a mapping")
    validate_plan(loaded)
    return loaded


def validate_plan(plan: dict[str, Any]) -> None:
    required = {"schema_version", "artist", "paths", "policy", "items", "summary"}
    if set(plan) != required or plan.get("schema_version") != SCHEMA_VERSION:
        raise MigrationError("unsupported or malformed migration plan schema")
    artist, paths, policy, summary, items = (
        plan["artist"],
        plan["paths"],
        plan["policy"],
        plan["summary"],
        plan["items"],
    )
    if not all(
        isinstance(value, dict) for value in (artist, paths, policy, summary)
    ) or not isinstance(items, list):
        raise MigrationError("plan sections have invalid types")
    if set(artist) != {"source_name", "destination_name"} or not all(
        isinstance(artist.get(key), str) and artist[key] for key in artist
    ):
        raise MigrationError("artist section is invalid")
    expected_path_keys = {
        "source_root",
        "template_root",
        "destination_root",
        "destination_artist_root",
    }
    if set(paths) != expected_path_keys or not all(
        isinstance(paths.get(key), str) and paths[key] for key in paths
    ):
        raise MigrationError("paths section is invalid")
    if policy != {
        "unknown_destination": TEMP_IMPORT,
        "preserve_original_filenames": True,
        "source_delete": False,
        "allow_new_categories": False,
    }:
        raise MigrationError("plan policy is not the fail-closed v0.1 policy")
    if set(summary) != {"source_files", "canonical_moves", "temp_import_moves"}:
        raise MigrationError("summary section is invalid")
    if (
        summary["source_files"] != len(items)
        or summary["canonical_moves"] != 0
        or summary["temp_import_moves"] != len(items)
    ):
        raise MigrationError("summary does not match v0.1 unresolved items")

    ids: set[str] = set()
    sources: set[Path] = set()
    destinations: set[Path] = set()
    for item in items:
        expected_item_keys = {
            "id",
            "source_relpath",
            "destination_relpath",
            "classification",
            "confidence",
            "reason",
        }
        if not isinstance(item, dict) or set(item) != expected_item_keys:
            raise MigrationError("item schema is invalid")
        item_id = item["id"]
        if (
            not isinstance(item_id, str)
            or not item_id.startswith("F")
            or not item_id[1:].isdigit()
        ):
            raise MigrationError(f"invalid item ID: {item_id!r}")
        source = normalized_relative(
            item["source_relpath"], f"item {item_id} source_relpath"
        )
        destination = normalized_relative(
            item["destination_relpath"], f"item {item_id} destination_relpath"
        )
        if item_id in ids or source in sources or destination in destinations:
            raise MigrationError(
                f"duplicate ID, source, or destination in plan item {item_id}"
            )
        expected_destination = Path(TEMP_IMPORT) / source
        if destination != expected_destination:
            raise MigrationError(
                f"item {item_id} must preserve source_relpath under {TEMP_IMPORT}"
            )
        if (
            item["classification"] != "UNRESOLVED"
            or item["confidence"] != "UNRESOLVED"
            or not isinstance(item["reason"], str)
            or not item["reason"]
        ):
            raise MigrationError(f"item {item_id} has unsupported classification")
        ids.add(item_id)
        sources.add(source)
        destinations.add(destination)
