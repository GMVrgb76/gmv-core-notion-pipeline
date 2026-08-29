#!/usr/bin/env python3
"""Create a reviewable, fail-closed GMV artist migration plan."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from gmv_artist_migrate_common import (
    MigrationError,
    SCHEMA_VERSION,
    TEMP_IMPORT,
    atomic_text_write,
    contained,
    normalized_relative,
    require_plain_directory,
    validate_plan,
    yaml_write,
)

SOURCE_RE = re.compile(r"^\*\*Source:\*\* `(?P<path>.+)`\s{2}$", re.MULTILINE)
COUNT_RE = re.compile(
    r"^\*\*Files successfully inventoried:\*\* (?P<count>\d+)\s{2}$", re.MULTILINE
)


def parse_folder_report(report: Path, source_root: Path) -> list[tuple[str, Path]]:
    if report.is_symlink() or not report.is_file():
        raise MigrationError(f"report missing or not a plain file: {report}")
    text = report.read_text(encoding="utf-8")
    source_match = SOURCE_RE.search(text)
    count_match = COUNT_RE.search(text)
    if not source_match or not count_match:
        raise MigrationError("report is missing source metadata or inventory count")
    report_source = Path(source_match.group("path")).expanduser().resolve(strict=False)
    if report_source != source_root.resolve():
        raise MigrationError(
            f"report source does not match supplied source folder: {report_source}"
        )
    if "Source scan complete: **YES**" not in text:
        raise MigrationError("report source scan is not complete")
    marker = "## Summary index\n"
    if marker not in text:
        raise MigrationError("report is missing Summary index")
    table = text.split(marker, 1)[1].split("\n## ", 1)[0]
    items: list[tuple[str, Path]] = []
    ids: set[str] = set()
    paths: set[Path] = set()
    for line in table.splitlines():
        if not line.startswith("| F"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) != 7:
            raise MigrationError(f"malformed Summary index row: {line}")
        item_id, _file_name, _kind, _size, _info, _master, source_path = cells
        if not re.fullmatch(r"F\d{4,}", item_id):
            raise MigrationError(f"invalid Summary index ID: {item_id!r}")
        relative = normalized_relative(source_path, f"report source path for {item_id}")
        if item_id in ids or relative in paths:
            raise MigrationError("report has duplicate IDs or source paths")
        ids.add(item_id)
        paths.add(relative)
        items.append((item_id, relative))
    if not items or len(items) != int(count_match.group("count")):
        raise MigrationError(
            "report Summary index does not match its inventoried file count"
        )
    return items


def markdown_plan(plan: dict) -> str:
    artist = plan["artist"]["destination_name"]
    paths = plan["paths"]
    lines = [
        f"# GMV Artist Migration Plan — {artist}",
        "",
        "Review this document, then use the adjacent YAML plan for execution.",
        "",
        "## Safety policy",
        "",
        "- All entries are unresolved and preserve their source-relative path under `09_TEMP_IMPORT`.",
        "- Original filenames are preserved; no source is modified by plan creation.",
        "- Apply moves files only after an interactive confirmation.",
        "",
        "## Paths",
        "",
        f"- Source: `{paths['source_root']}`",
        f"- Template: `{paths['template_root']}`",
        f"- Destination: `{paths['destination_artist_root']}`",
        "",
        "## Items",
        "",
        "| ID | Source | Destination | Classification |",
        "|---|---|---|---|",
    ]
    for item in plan["items"]:
        lines.append(
            f"| {item['id']} | `{item['source_relpath']}` | `{item['destination_relpath']}` | UNRESOLVED |"
        )
    lines.extend(
        [
            "",
            f"Total: {plan['summary']['source_files']} files; 0 canonical moves; {plan['summary']['temp_import_moves']} TEMP_IMPORT moves.",
            "",
        ]
    )
    return "\n".join(lines)


def build_plan(
    source_folder: Path,
    report: Path,
    template: Path,
    artist: str,
    destination_root: Path,
) -> dict:
    source_root = require_plain_directory(source_folder.expanduser(), "source folder")
    template_root = require_plain_directory(template.expanduser(), "template")
    destination_root = require_plain_directory(
        destination_root.expanduser(), "destination root"
    )
    if not artist or Path(artist).name != artist or artist in {".", ".."}:
        raise MigrationError(
            "artist destination name must be a single non-empty folder name"
        )
    destination_artist_root = destination_root / artist
    contained(destination_root, destination_artist_root, "destination artist root")
    if destination_artist_root.exists():
        raise MigrationError(
            f"destination artist root already exists: {destination_artist_root}"
        )
    report_items = parse_folder_report(report.expanduser(), source_root)
    items = []
    destinations: set[Path] = set()
    for item_id, relative in report_items:
        destination = Path(TEMP_IMPORT) / relative
        if destination in destinations:
            raise MigrationError(
                f"unresolved destination collision: {destination.as_posix()}"
            )
        destinations.add(destination)
        items.append(
            {
                "id": item_id,
                "source_relpath": relative.as_posix(),
                "destination_relpath": destination.as_posix(),
                "classification": "UNRESOLVED",
                "confidence": "UNRESOLVED",
                "reason": "No approved canonical destination supplied; source-relative path preserved under TEMP_IMPORT.",
            }
        )
    plan = {
        "schema_version": SCHEMA_VERSION,
        "artist": {"source_name": source_root.name, "destination_name": artist},
        "paths": {
            "source_root": str(source_root),
            "template_root": str(template_root),
            "destination_root": str(destination_root),
            "destination_artist_root": str(destination_artist_root),
        },
        "policy": {
            "unknown_destination": TEMP_IMPORT,
            "preserve_original_filenames": True,
            "source_delete": False,
            "allow_new_categories": False,
        },
        "items": items,
        "summary": {
            "source_files": len(items),
            "canonical_moves": 0,
            "temp_import_moves": len(items),
        },
    }
    validate_plan(plan)
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_folder", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--artist", required=True)
    parser.add_argument("--destination-root", required=True, type=Path)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="authoritative YAML output (default: current directory)",
    )
    args = parser.parse_args(argv)
    try:
        plan = build_plan(
            args.source_folder,
            args.report,
            args.template,
            args.artist,
            args.destination_root,
        )
        output = (
            args.output or (Path.cwd() / f"{args.artist}_MIGRATION_PLAN.yaml")
        ).expanduser()
        if output.suffix.lower() not in {".yaml", ".yml"}:
            raise MigrationError("plan output must end in .yaml or .yml")
        if output.exists():
            raise MigrationError(f"refusing to overwrite existing plan: {output}")
        markdown_output = output.with_suffix(".md")
        if markdown_output.exists():
            raise MigrationError(
                f"refusing to overwrite existing review output: {markdown_output}"
            )
        yaml_write(output, plan)
        atomic_text_write(markdown_output, markdown_plan(plan))
    except (MigrationError, OSError) as exc:
        parser.error(str(exc))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
