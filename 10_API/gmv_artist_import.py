#!/usr/bin/env python3
"""Run the GMV artist import workflow with one user confirmation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

CORE_ROOT = Path(os.environ.get("GMV_CORE_ROOT", Path.home() / ".gmv_core"))
API_ROOT = CORE_ROOT / "10_API"
QA_ROOT = CORE_ROOT / "area35-qa"
DEFAULT_TEMPLATE = Path.home() / "Library/CloudStorage/Dropbox/TEMPLATES/CARTELLA TEMPLATES/ARTIST_TEMPLATE"
DEFAULT_DESTINATION_ROOT = Path.home() / "Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS"
FOLDER_REPORT = API_ROOT / "gmv_folder_report.py"
MIGRATE_PLAN = API_ROOT / "gmv_artist_migrate_plan.py"
MIGRATE_APPLY = API_ROOT / "gmv_artist_migrate_apply.py"


def canonical_artist_name(source_name: str) -> str:
    parts = [part for part in source_name.strip().split() if part]
    if len(parts) < 2:
        raise ValueError(f"cannot derive canonical artist name from: {source_name!r}")
    return f"{parts[-1].upper()}_{'_'.join(part.capitalize() for part in parts[:-1])}"


def plain_artist_name(value: str) -> str:
    if not value or Path(value).name != value or value in {".", ".."}:
        raise ValueError("artist name must be one non-empty folder name")
    return value


def run(command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=input_text, text=True, capture_output=True, check=False)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regular_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_file():
            found.append(path)
    return sorted(found, key=lambda path: path.as_posix().casefold())


def artifact_error(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stderr or completed.stdout or "unknown component failure").strip()


def write_final_report(path: Path, result: dict[str, Any]) -> None:
    lines = [
        f"# GMV Artist Import — {result['artist']}",
        "",
        f"**Status:** {result['status']}",
        "",
        f"- Source: `{result['source']}`",
        f"- Destination: `{result['destination']}`",
        f"- Files found: {result['source_files']}",
        f"- Files moved: {result['moved']}",
        f"- TEMP_IMPORT: {result['temp_import']}",
        f"- Failures: {result['failed']}",
        f"- SHA-256 verified: {result['verified']}/{result['source_files']}",
        f"- Source regular files remaining: {result['source_remaining']}",
        "",
        "## Run evidence",
        "",
        f"`{result['run_dir']}`",
    ]
    if result["notes"]:
        lines.extend(["", "## Notes", ""] + [f"- {note}" for note in result["notes"]])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def result_payload(status: str, source: Path, destination: Path, run_dir: Path, *, source_files: int = 0, moved: int = 0, temp_import: int = 0, failed: int = 0, verified: int = 0, source_remaining: int = 0, notes: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status, "artist": destination.name, "source": str(source),
        "destination": str(destination), "run_dir": str(run_dir),
        "source_files": source_files, "moved": moved, "temp_import": temp_import,
        "failed": failed, "verified": verified, "source_remaining": source_remaining,
        "notes": notes or [],
    }


def abort(final_report: Path, result: dict[str, Any]) -> int:
    write_final_report(final_report, result)
    print(f"GMV ARTIST IMPORT — {result['status']}\n\nReport: {final_report}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_folder", type=Path)
    parser.add_argument("--artist")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--destination-root", type=Path, default=DEFAULT_DESTINATION_ROOT)
    parser.add_argument("--qa-root", type=Path, default=QA_ROOT)
    args = parser.parse_args(argv)
    source = args.source_folder.expanduser()
    if source.is_symlink() or not source.is_dir():
        parser.error(f"source must be an existing non-symlink directory: {source}")
    source = source.resolve()
    try:
        artist = plain_artist_name(args.artist or canonical_artist_name(source.name))
    except ValueError as exc:
        parser.error(str(exc))
    template, destination_root, qa_root = (args.template.expanduser(), args.destination_root.expanduser(), args.qa_root.expanduser())
    if template.is_symlink() or not template.is_dir():
        parser.error(f"template must be an existing non-symlink directory: {template}")
    if destination_root.is_symlink() or not destination_root.is_dir():
        parser.error(f"destination root must be an existing non-symlink directory: {destination_root}")
    for component in (FOLDER_REPORT, MIGRATE_PLAN, MIGRATE_APPLY):
        if not component.is_file():
            parser.error(f"required GMV component missing: {component}")
    destination = destination_root.resolve() / artist
    if destination.exists() or destination.is_symlink():
        parser.error(f"destination artist already exists: {destination}")

    print("GMV ARTIST IMPORT")
    print(f"Source: {source}")
    print(f"Destination artist: {artist}")
    if input("Proceed? [y/N] ").strip().lower() not in {"y", "yes"}:
        print("GMV ARTIST IMPORT — ABORTED")
        return 2

    run_id = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir = qa_root.resolve() / "imports" / f"{run_id}_{artist}"
    run_dir.mkdir(parents=True, exist_ok=False)
    report_path, plan_path, result_base = run_dir / "SOURCE_REPORT.md", run_dir / "MIGRATION_PLAN.yaml", run_dir / "MIGRATION_RESULT"
    final_report = run_dir / "IMPORT_REPORT.md"

    report_run = run([sys.executable, str(FOLDER_REPORT), str(source), "--output", str(report_path)])
    if report_run.returncode:
        return abort(final_report, result_payload("ABORTED", source, destination, run_dir, source_remaining=len(regular_files(source)), notes=[artifact_error(report_run)]))
    source_paths = regular_files(source)
    if not source_paths:
        return abort(final_report, result_payload("ABORTED", source, destination, run_dir, notes=["folder-report completed but source has no regular files"]))
    pre_hashes = {path.relative_to(source).as_posix(): sha256(path) for path in source_paths}
    (run_dir / "PRE_MIGRATION_HASHES.json").write_text(json.dumps(pre_hashes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    plan_run = run([sys.executable, str(MIGRATE_PLAN), str(source), "--report", str(report_path), "--template", str(template), "--artist", artist, "--destination-root", str(destination_root), "-o", str(plan_path)])
    if plan_run.returncode:
        return abort(final_report, result_payload("ABORTED", source, destination, run_dir, source_files=len(source_paths), source_remaining=len(regular_files(source)), notes=[artifact_error(plan_run)]))
    # The planner writes the required sibling review artifact.
    if not plan_path.with_suffix(".md").is_file():
        return abort(final_report, result_payload("ABORTED", source, destination, run_dir, source_files=len(source_paths), source_remaining=len(regular_files(source)), notes=["planner did not write MIGRATION_PLAN.md"]))

    apply_run = run([sys.executable, str(MIGRATE_APPLY), str(plan_path), "--result-output", str(result_base)], input_text="y\n")
    result_path = result_base.with_suffix(".json")
    if not result_path.is_file():
        status = "PARTIAL" if destination.exists() else "ABORTED"
        return abort(final_report, result_payload(status, source, destination, run_dir, source_files=len(source_paths), failed=1, source_remaining=len(regular_files(source)), notes=[artifact_error(apply_run), "migration result ledger missing"]))
    migration_result = json.loads(result_path.read_text(encoding="utf-8"))
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    verified = 0
    for item in plan["items"]:
        original = item["source_relpath"]
        target = destination / Path(item["destination_relpath"])
        if target.is_file() and sha256(target) == pre_hashes.get(original):
            verified += 1
    source_remaining = len(regular_files(source))
    moved, failed = int(migration_result["moved_item_count"]), int(migration_result["failed_item_count"])
    temp_import = sum(1 for item in plan["items"] if Path(item["destination_relpath"]).parts[0] == "09_TEMP_IMPORT")
    completed = migration_result["status"] == "COMPLETED" and moved == len(source_paths) and failed == 0 and source_remaining == 0 and verified == len(source_paths)
    final_status = "COMPLETED" if completed else ("PARTIAL" if moved else "ABORTED")
    notes = [] if apply_run.returncode == 0 else [artifact_error(apply_run)]
    result = result_payload(final_status, source, destination, run_dir, source_files=len(source_paths), moved=moved, temp_import=temp_import, failed=failed, verified=verified, source_remaining=source_remaining, notes=notes)
    write_final_report(final_report, result)
    print(f"GMV ARTIST IMPORT — {final_status}\n\nArtist: {artist}\nFiles: {moved}/{len(source_paths)}\nTEMP_IMPORT: {temp_import}\nErrors: {failed}\nIntegrity: {'VERIFIED' if verified == len(source_paths) else f'{verified}/{len(source_paths)}'}\n\nReport: {final_report}")
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
