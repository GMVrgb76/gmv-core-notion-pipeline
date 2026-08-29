#!/usr/bin/env python3
"""Create a local, fail-closed, plan-only GMV artist normalization proposal."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Callable, Iterable
import urllib.error
import urllib.parse
import urllib.request

from gmv_artist_migrate_common import (
    MigrationError,
    TEMP_IMPORT,
    atomic_text_write,
    contained,
    json_write,
    normalized_relative,
    require_plain_directory,
    sha256_file,
)

NORMALIZATION_SCHEMA_VERSION = "gmv.artist-normalization-plan.v0.1"
MODE = "PLAN_ONLY"
DEFAULT_MODEL = "qwen3:8b"
DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT = 60.0
DEFAULT_BATCH_SIZE = 40
MAX_BATCH_SIZE = 200
MAX_TIMEOUT = 600.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_REASON_LENGTH = 1000
DEFAULT_TEMPLATE = Path(
    "~/Library/CloudStorage/Dropbox/TEMPLATES/CARTELLA TEMPLATES/ARTIST_TEMPLATE"
)


class NormalizationError(MigrationError):
    """A normalization input or model response violates the plan-only contract."""


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Prevent a loopback Ollama endpoint from redirecting to another host."""

    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            f"Ollama redirect refused: {new_url}",
            headers,
            file_pointer,
        )


def open_loopback(request: urllib.request.Request, timeout: float) -> Any:
    opener = urllib.request.build_opener(RejectRedirects())
    return opener.open(request, timeout=timeout)  # noqa: S310 - exact URL validated


def core_root() -> Path:
    return Path(os.environ.get("GMV_CORE_ROOT", Path.home() / ".gmv_core")).expanduser()


def default_output_root() -> Path:
    return core_root() / "area35-qa" / "normalizations"


def validate_runtime_options(
    endpoint: str, model: str, timeout: float, batch_size: int
) -> str:
    parsed = urllib.parse.urlsplit(endpoint)
    try:
        port = parsed.port
    except ValueError as exc:
        raise NormalizationError(f"invalid Ollama endpoint: {endpoint!r}") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or port != 11434
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise NormalizationError(
            "Ollama endpoint must be http://127.0.0.1:11434 or http://localhost:11434"
        )
    if not isinstance(model, str) or not model.strip() or len(model) > 200:
        raise NormalizationError("Ollama model must be a non-empty name")
    if not 0 < timeout <= MAX_TIMEOUT:
        raise NormalizationError(
            f"timeout must be greater than 0 and at most {MAX_TIMEOUT:g}"
        )
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise NormalizationError(f"batch size must be between 1 and {MAX_BATCH_SIZE}")
    return endpoint.rstrip("/")


def _walk(root: Path, label: str) -> Iterable[tuple[Path, list[str], list[str]]]:
    def on_error(error: OSError) -> None:
        raise NormalizationError(f"cannot inventory {label}: {error}")

    for current, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False, onerror=on_error
    ):
        current_path = Path(current)
        if current_path.is_symlink():
            raise NormalizationError(
                f"{label} contains a symlink directory: {current_path}"
            )
        directory_names.sort(key=str.casefold)
        file_names.sort(key=str.casefold)
        for name in directory_names + file_names:
            candidate = current_path / name
            if candidate.is_symlink():
                raise NormalizationError(f"{label} contains a symlink: {candidate}")
        yield current_path, directory_names, file_names


def inventory_temp_import(temp_root: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for current, _directory_names, file_names in _walk(temp_root, TEMP_IMPORT):
        for name in file_names:
            path = current / name
            if not path.is_file():
                raise NormalizationError(
                    f"{TEMP_IMPORT} contains a non-regular filesystem entry: {path}"
                )
            relative = normalized_relative(
                path.relative_to(temp_root).as_posix(), "TEMP_IMPORT source_relpath"
            )
            before = path.stat(follow_symlinks=False)
            digest = sha256_file(path)
            after = path.stat(follow_symlinks=False)
            before_state = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            )
            after_state = (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            )
            if before_state != after_state:
                raise NormalizationError(f"source changed during inventory: {relative}")
            inventory.append(
                {
                    "source_relpath": relative.as_posix(),
                    "size_bytes": after.st_size,
                    "extension": path.suffix.lower(),
                    "sha256": digest,
                }
            )
    inventory.sort(key=lambda item: item["source_relpath"].casefold())
    sources = [item["source_relpath"] for item in inventory]
    if len(sources) != len(set(sources)):
        raise NormalizationError(
            "TEMP_IMPORT inventory contains duplicate source paths"
        )
    return inventory


def allowed_destination_directories(template_root: Path) -> list[str]:
    allowed: set[str] = set()
    for current, directory_names, _file_names in _walk(
        template_root, "artist template"
    ):
        relative = current.relative_to(template_root)
        if relative != Path("."):
            normalized = normalized_relative(
                relative.as_posix(), "template destination directory"
            ).as_posix()
            if normalized == TEMP_IMPORT or not normalized.startswith(
                f"{TEMP_IMPORT}/"
            ):
                allowed.add(normalized)
        # All descendants are still walked so a template symlink cannot be hidden
        # beneath the reserved TEMP_IMPORT branch.
        directory_names[:] = sorted(directory_names, key=str.casefold)
    if TEMP_IMPORT not in allowed:
        raise NormalizationError(
            f"template is missing required directory: {TEMP_IMPORT}"
        )
    return sorted(allowed, key=str.casefold)


def batches(items: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def ollama_request_payload(
    model: str, files: list[dict[str, Any]], allowed: list[str]
) -> dict[str, Any]:
    task = {
        "task": (
            "Classify every supplied file into exactly one allowed destination "
            "directory. Use 09_TEMP_IMPORT with status UNRESOLVED when uncertain. "
            "Return JSON only and propose no filesystem operation."
        ),
        "allowed_destination_directories": allowed,
        "response_schema": {
            "items": [
                {
                    "source_relpath": "exact source_relpath from files",
                    "destination_directory": "one allowed destination directory",
                    "status": "PROPOSED or UNRESOLVED",
                    "confidence": "HIGH, MEDIUM, or LOW",
                    "reason": "non-empty string",
                }
            ]
        },
        "files": [
            {
                "source_relpath": item["source_relpath"],
                "size_bytes": item["size_bytes"],
                "extension": item["extension"],
            }
            for item in files
        ],
    }
    return {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {
                "role": "user",
                "content": json.dumps(task, ensure_ascii=False, separators=(",", ":")),
            }
        ],
    }


def decode_ollama_response(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise NormalizationError("Ollama response exceeds the configured size limit")
    try:
        envelope = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NormalizationError("Ollama returned malformed JSON") from exc
    if not isinstance(envelope, dict):
        raise NormalizationError("Ollama response envelope must be an object")
    message = envelope.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise NormalizationError("Ollama response envelope is missing message.content")
    try:
        content = json.loads(message["content"])
    except json.JSONDecodeError as exc:
        raise NormalizationError("Ollama message.content is not valid JSON") from exc
    if not isinstance(content, dict):
        raise NormalizationError("Ollama message.content must decode to an object")
    return content


def query_ollama(
    endpoint: str,
    model: str,
    timeout: float,
    files: list[dict[str, Any]],
    allowed: list[str],
) -> dict[str, Any]:
    endpoint = validate_runtime_options(endpoint, model, timeout, len(files) or 1)
    body = json.dumps(
        ollama_request_payload(model, files, allowed),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - endpoint is exact validated loopback
        endpoint + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with open_loopback(request, timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NormalizationError(f"local Ollama request failed: {exc}") from exc
    return decode_ollama_response(raw)


def unresolved_item(source: dict[str, Any], reason: str) -> dict[str, Any]:
    relative = normalized_relative(source["source_relpath"], "source_relpath")
    destination = Path(TEMP_IMPORT) / relative
    return {
        "source_relpath": relative.as_posix(),
        "source_sha256": source["sha256"],
        "destination_directory": TEMP_IMPORT,
        "destination_relpath": destination.as_posix(),
        "status": "UNRESOLVED",
        "confidence": "LOW",
        "reason": reason,
    }


def validate_batch_response(
    raw: Any, expected: list[dict[str, Any]], allowed: set[str]
) -> list[dict[str, Any]]:
    if (
        not isinstance(raw, dict)
        or set(raw) != {"items"}
        or not isinstance(raw["items"], list)
    ):
        raise NormalizationError(
            "Ollama content does not match the required root schema"
        )
    if len(raw["items"]) != len(expected):
        raise NormalizationError("Ollama returned missing or extra items")

    expected_by_source = {item["source_relpath"]: item for item in expected}
    response_by_source: dict[str, dict[str, Any]] = {}
    required_keys = {
        "source_relpath",
        "destination_directory",
        "status",
        "confidence",
        "reason",
    }
    for item in raw["items"]:
        if not isinstance(item, dict) or set(item) != required_keys:
            raise NormalizationError("Ollama item does not match the required schema")
        try:
            source = normalized_relative(
                item["source_relpath"], "Ollama source_relpath"
            ).as_posix()
        except MigrationError as exc:
            raise NormalizationError(str(exc)) from exc
        if source not in expected_by_source:
            raise NormalizationError(f"Ollama returned an unexpected source: {source}")
        if source in response_by_source:
            raise NormalizationError(f"Ollama returned a duplicate source: {source}")
        response_by_source[source] = item
    if set(response_by_source) != set(expected_by_source):
        raise NormalizationError("Ollama omitted one or more expected sources")

    validated = []
    for source in expected:
        source_relpath = source["source_relpath"]
        item = response_by_source[source_relpath]
        destination_value = item["destination_directory"]
        status = item["status"]
        confidence = item["confidence"]
        reason = item["reason"]
        try:
            destination_directory = normalized_relative(
                destination_value, f"Ollama destination for {source_relpath}"
            ).as_posix()
        except MigrationError, TypeError:
            validated.append(unresolved_item(source, "LLM_DESTINATION_INVALID"))
            continue
        valid_reason = (
            isinstance(reason, str)
            and bool(reason.strip())
            and len(reason) <= MAX_REASON_LENGTH
        )
        valid = (
            destination_directory in allowed
            and status in {"PROPOSED", "UNRESOLVED"}
            and confidence in {"HIGH", "MEDIUM", "LOW"}
            and valid_reason
            and ((destination_directory == TEMP_IMPORT) == (status == "UNRESOLVED"))
        )
        if not valid:
            validated.append(unresolved_item(source, "LLM_ITEM_INVALID"))
            continue
        source_path = normalized_relative(source_relpath, "source_relpath")
        destination_relpath = Path(destination_directory) / source_path
        validated.append(
            {
                "source_relpath": source_path.as_posix(),
                "source_sha256": source["sha256"],
                "destination_directory": destination_directory,
                "destination_relpath": destination_relpath.as_posix(),
                "status": status,
                "confidence": confidence,
                "reason": reason.strip(),
            }
        )
    return validated


def validate_normalization_plan(plan: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "mode",
        "created_at",
        "artist_folder",
        "template_folder",
        "model",
        "endpoint",
        "batch_size",
        "allowed_destination_directories",
        "items",
        "summary",
        "safety",
    }
    if (
        set(plan) != required
        or plan.get("schema_version") != NORMALIZATION_SCHEMA_VERSION
    ):
        raise NormalizationError("normalization plan has an unsupported schema")
    if plan.get("mode") != MODE:
        raise NormalizationError("normalization plan is not PLAN_ONLY")
    if not isinstance(plan.get("items"), list):
        raise NormalizationError("normalization plan items must be a list")
    allowed_values = plan.get("allowed_destination_directories")
    if not isinstance(allowed_values, list) or any(
        not isinstance(value, str) for value in allowed_values
    ):
        raise NormalizationError("allowed destination directories are invalid")
    allowed = set(allowed_values)
    if len(allowed) != len(allowed_values) or TEMP_IMPORT not in allowed:
        raise NormalizationError(
            "allowed destination directories are incomplete or duplicate"
        )
    if plan.get("safety") != {
        "files_modified": 0,
        "operations_applied": 0,
        "operation_types": [],
    }:
        raise NormalizationError("normalization safety declaration is invalid")

    sources: set[Path] = set()
    destinations: set[Path] = set()
    proposed = 0
    unresolved = 0
    expected_keys = {
        "id",
        "source_relpath",
        "source_sha256",
        "destination_directory",
        "destination_relpath",
        "status",
        "confidence",
        "reason",
    }
    for index, item in enumerate(plan["items"], 1):
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise NormalizationError("normalization plan item schema is invalid")
        if item["id"] != f"N{index:04d}":
            raise NormalizationError(
                "normalization plan item IDs are not deterministic"
            )
        source = normalized_relative(
            item["source_relpath"], f"item {item['id']} source"
        )
        destination_directory = normalized_relative(
            item["destination_directory"], f"item {item['id']} destination directory"
        )
        destination = normalized_relative(
            item["destination_relpath"], f"item {item['id']} destination"
        )
        if source in sources or destination in destinations:
            raise NormalizationError(
                "normalization plan has duplicate source or destination paths"
            )
        if destination_directory.as_posix() not in allowed:
            raise NormalizationError(
                "normalization plan uses a destination outside the template"
            )
        if destination != destination_directory / source:
            raise NormalizationError(
                "normalization destination does not preserve source_relpath"
            )
        status = item["status"]
        if status == "UNRESOLVED":
            unresolved += 1
            if (
                destination_directory != Path(TEMP_IMPORT)
                or item["confidence"] != "LOW"
            ):
                raise NormalizationError("UNRESOLVED item violates TEMP_IMPORT policy")
        elif status == "PROPOSED":
            proposed += 1
            if destination_directory == Path(TEMP_IMPORT):
                raise NormalizationError("PROPOSED item cannot target TEMP_IMPORT")
        else:
            raise NormalizationError("normalization item has an invalid status")
        if item["confidence"] not in {"HIGH", "MEDIUM", "LOW"}:
            raise NormalizationError("normalization item has invalid confidence")
        if not isinstance(item["source_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", item["source_sha256"]
        ):
            raise NormalizationError("normalization item has an invalid SHA-256")
        if not isinstance(item["reason"], str) or not item["reason"]:
            raise NormalizationError("normalization item reason is invalid")
        sources.add(source)
        destinations.add(destination)

    expected_summary = {
        "source_files": len(plan["items"]),
        "proposed": proposed,
        "unresolved": unresolved,
        "operations_applied": 0,
    }
    if plan.get("summary") != expected_summary:
        raise NormalizationError("normalization summary does not match plan items")


QueryFunction = Callable[
    [str, str, float, list[dict[str, Any]], list[str]], dict[str, Any]
]


def build_plan(
    artist_folder: Path,
    template: Path,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = DEFAULT_TIMEOUT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    query_fn: QueryFunction | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    endpoint = validate_runtime_options(endpoint, model, timeout, batch_size)
    artist = require_plain_directory(artist_folder.expanduser(), "artist folder")
    template_root = require_plain_directory(template.expanduser(), "artist template")
    temp_candidate = artist / TEMP_IMPORT
    if temp_candidate.is_symlink():
        raise NormalizationError(f"{TEMP_IMPORT} must not be a symlink")
    temp_root = require_plain_directory(temp_candidate, TEMP_IMPORT)
    if temp_root.parent != artist:
        raise NormalizationError(f"{TEMP_IMPORT} escapes the artist folder")
    contained(artist, temp_root, TEMP_IMPORT)

    inventory = inventory_temp_import(temp_root)
    allowed = allowed_destination_directories(template_root)
    proposals: list[dict[str, Any]] = []
    active_query = query_fn or query_ollama
    for batch in batches(inventory, batch_size):
        raw = active_query(endpoint, model, timeout, batch, allowed)
        proposals.extend(validate_batch_response(raw, batch, set(allowed)))
    for index, item in enumerate(proposals, 1):
        item["id"] = f"N{index:04d}"

    created_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    plan = {
        "schema_version": NORMALIZATION_SCHEMA_VERSION,
        "mode": MODE,
        "created_at": created_at.isoformat(timespec="seconds"),
        "artist_folder": str(artist),
        "template_folder": str(template_root),
        "model": model,
        "endpoint": endpoint,
        "batch_size": batch_size,
        "allowed_destination_directories": allowed,
        "items": proposals,
        "summary": {
            "source_files": len(proposals),
            "proposed": sum(item["status"] == "PROPOSED" for item in proposals),
            "unresolved": sum(item["status"] == "UNRESOLVED" for item in proposals),
            "operations_applied": 0,
        },
        "safety": {
            "files_modified": 0,
            "operations_applied": 0,
            "operation_types": [],
        },
    }
    validate_normalization_plan(plan)
    return plan


def markdown_plan(plan: dict[str, Any]) -> str:
    def escape(value: object) -> str:
        return str(value).replace("\\", "\\\\").replace("|", r"\|").replace("\n", " ")

    summary = plan["summary"]
    lines = [
        f"# GMV Artist Normalization Plan — {Path(plan['artist_folder']).name}",
        "",
        "**Mode:** PLAN_ONLY  ",
        f"**Created:** {plan['created_at']}  ",
        f"**Source files:** {summary['source_files']}  ",
        f"**Proposed:** {summary['proposed']}  ",
        f"**Unresolved:** {summary['unresolved']}  ",
        "**Operations applied:** 0",
        "",
        "## Items",
        "",
        "| ID | Source relative path | Destination relative path | Status | Confidence | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for item in plan["items"]:
        lines.append(
            "| "
            + " | ".join(
                escape(item[key])
                for key in (
                    "id",
                    "source_relpath",
                    "destination_relpath",
                    "status",
                    "confidence",
                    "reason",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Safety declaration",
            "",
            "This artifact is a proposal only.",
            "No artist or template file was created, moved, renamed, overwritten or deleted.",
            "",
        ]
    )
    return "\n".join(lines)


def artist_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return slug or "artist"


def write_plan(
    plan: dict[str, Any], output_root: Path, run_id: str | None = None
) -> Path:
    validate_normalization_plan(plan)
    if output_root.is_symlink():
        raise NormalizationError(
            f"normalization output root must not be a symlink: {output_root}"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    root = require_plain_directory(output_root, "normalization output root")
    generated_run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", generated_run_id):
        raise NormalizationError("normalization run ID contains unsupported characters")
    name = f"{generated_run_id}_{artist_slug(Path(plan['artist_folder']).name)}"
    destination = root / name
    contained(root, destination, "normalization run directory")
    if destination.exists() or destination.is_symlink():
        raise NormalizationError(
            f"normalization run directory already exists: {destination}"
        )
    staging = root / f".{name}.staging"
    if staging.exists() or staging.is_symlink():
        raise NormalizationError(
            f"normalization staging directory already exists: {staging}"
        )
    staging.mkdir(mode=0o700)
    try:
        json_write(staging / "NORMALIZATION_PLAN.json", plan)
        atomic_text_write(staging / "NORMALIZATION_PLAN.md", markdown_plan(plan))
        os.replace(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artist_folder", type=Path)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args(argv)
    try:
        args.endpoint = validate_runtime_options(
            args.endpoint, args.model, args.timeout, args.batch_size
        )
    except NormalizationError as exc:
        parser.error(str(exc))
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_root = default_output_root()
    try:
        resolved_core = core_root().resolve(strict=False)
        contained(resolved_core, output_root, "normalization output root")
        plan = build_plan(
            args.artist_folder,
            args.template,
            model=args.model,
            endpoint=args.endpoint,
            timeout=args.timeout,
            batch_size=args.batch_size,
        )
        output = write_plan(plan, output_root)
    except (MigrationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
