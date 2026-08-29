from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "10_API"
sys.path.insert(0, str(API_ROOT))
SPEC = importlib.util.spec_from_file_location(
    "gmv_artist_normalize_plan", API_ROOT / "gmv_artist_normalize_plan.py"
)
assert SPEC and SPEC.loader
NORMALIZE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NORMALIZE)


def layout(tmp_path: Path) -> tuple[Path, Path]:
    artist = tmp_path / "MANOS_Gaspare"
    temp = artist / "09_TEMP_IMPORT"
    (temp / "a").mkdir(parents=True)
    (temp / "b").mkdir()
    (temp / "a" / "IMG_5378.jpg").write_bytes(b"from-a")
    (temp / "b" / "IMG_5378.jpg").write_bytes(b"from-b")
    template = tmp_path / "ARTIST_TEMPLATE"
    (template / "07_CAREER" / "02_CV").mkdir(parents=True)
    (template / "04_WORKS" / "01_IMAGES").mkdir(parents=True)
    (template / "09_TEMP_IMPORT").mkdir()
    return artist, template


def snapshot(root: Path) -> list[tuple[str, str, bytes | str]]:
    result: list[tuple[str, str, bytes | str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result.append((relative, "symlink", os.readlink(path)))
        elif path.is_dir():
            result.append((relative, "directory", ""))
        elif path.is_file():
            result.append((relative, "file", path.read_bytes()))
        else:
            result.append((relative, "special", ""))
    return result


def response_for(
    files: list[dict[str, Any]], destination: str = "04_WORKS/01_IMAGES"
) -> dict[str, Any]:
    return {
        "items": [
            {
                "source_relpath": item["source_relpath"],
                "destination_directory": destination,
                "status": "PROPOSED"
                if destination != "09_TEMP_IMPORT"
                else "UNRESOLVED",
                "confidence": "HIGH" if destination != "09_TEMP_IMPORT" else "LOW",
                "reason": "fixture classification",
            }
            for item in files
        ]
    }


def build(
    artist: Path,
    template: Path,
    query_fn: NORMALIZE.QueryFunction,
    batch_size: int = 40,
) -> dict[str, Any]:
    return NORMALIZE.build_plan(
        artist,
        template,
        batch_size=batch_size,
        query_fn=query_fn,
        now=datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
    )


def test_valid_classification_preserves_nested_duplicate_names(tmp_path: Path) -> None:
    artist, template = layout(tmp_path)
    before = snapshot(artist)

    plan = build(
        artist,
        template,
        lambda _endpoint, _model, _timeout, files, _allowed: response_for(files),
    )

    assert [item["source_relpath"] for item in plan["items"]] == [
        "a/IMG_5378.jpg",
        "b/IMG_5378.jpg",
    ]
    assert [item["destination_relpath"] for item in plan["items"]] == [
        "04_WORKS/01_IMAGES/a/IMG_5378.jpg",
        "04_WORKS/01_IMAGES/b/IMG_5378.jpg",
    ]
    assert plan["summary"] == {
        "source_files": 2,
        "proposed": 2,
        "unresolved": 0,
        "operations_applied": 0,
    }
    assert plan["mode"] == "PLAN_ONLY"
    assert snapshot(artist) == before


def test_multiple_batches_preserve_deterministic_global_order(tmp_path: Path) -> None:
    artist, template = layout(tmp_path)
    temp = artist / "09_TEMP_IMPORT"
    for name in ("c.txt", "d.txt", "e.txt"):
        (temp / name).write_text(name, encoding="utf-8")
    calls: list[list[str]] = []

    def query(
        _endpoint: str,
        _model: str,
        _timeout: float,
        files: list[dict[str, Any]],
        _allowed: list[str],
    ) -> dict[str, Any]:
        calls.append([item["source_relpath"] for item in files])
        response = response_for(files)
        response["items"].reverse()
        return response

    plan = build(artist, template, query, batch_size=2)

    assert len(calls) == 3
    assert [item["source_relpath"] for item in plan["items"]] == sorted(
        [item["source_relpath"] for item in plan["items"]], key=str.casefold
    )
    assert [item["id"] for item in plan["items"]] == [
        "N0001",
        "N0002",
        "N0003",
        "N0004",
        "N0005",
    ]


def test_invented_destination_becomes_unresolved_with_full_source_path(
    tmp_path: Path,
) -> None:
    artist, template = layout(tmp_path)

    def query(
        _endpoint: str,
        _model: str,
        _timeout: float,
        files: list[dict[str, Any]],
        _allowed: list[str],
    ) -> dict[str, Any]:
        response = response_for(files)
        response["items"][0]["destination_directory"] = "INVENTED/CATEGORY"
        return response

    plan = build(artist, template, query)
    item = plan["items"][0]
    assert item["status"] == "UNRESOLVED"
    assert item["confidence"] == "LOW"
    assert item["destination_relpath"] == "09_TEMP_IMPORT/a/IMG_5378.jpg"


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "CERTAIN"), ("confidence", "CERTAIN"), ("reason", "")],
)
def test_invalid_model_item_fields_become_unresolved(
    tmp_path: Path, field: str, value: str
) -> None:
    artist, template = layout(tmp_path)

    def query(
        _endpoint: str,
        _model: str,
        _timeout: float,
        files: list[dict[str, Any]],
        _allowed: list[str],
    ) -> dict[str, Any]:
        response = response_for(files)
        response["items"][0][field] = value
        return response

    plan = build(artist, template, query)
    assert plan["items"][0]["status"] == "UNRESOLVED"
    assert plan["items"][0]["destination_relpath"] == "09_TEMP_IMPORT/a/IMG_5378.jpg"


@pytest.mark.parametrize("mode", ["missing", "extra", "duplicate"])
def test_missing_extra_or_duplicate_model_item_aborts_plan(
    tmp_path: Path, mode: str
) -> None:
    artist, template = layout(tmp_path)

    def query(
        _endpoint: str,
        _model: str,
        _timeout: float,
        files: list[dict[str, Any]],
        _allowed: list[str],
    ) -> dict[str, Any]:
        response = response_for(files)
        if mode == "missing":
            response["items"].pop()
        elif mode == "extra":
            response["items"].append(
                {
                    **response["items"][0],
                    "source_relpath": "extra/file.jpg",
                }
            )
        else:
            response["items"][1]["source_relpath"] = response["items"][0][
                "source_relpath"
            ]
        return response

    with pytest.raises(NORMALIZE.NormalizationError):
        build(artist, template, query)


@pytest.mark.parametrize(
    "raw",
    [None, [], {}, {"items": "bad"}, {"items": [], "unexpected": True}],
)
def test_malformed_model_content_aborts_plan(tmp_path: Path, raw: Any) -> None:
    artist, template = layout(tmp_path)
    with pytest.raises(NORMALIZE.NormalizationError):
        build(artist, template, lambda *_args: raw)


@pytest.mark.parametrize("source", ["../escape.jpg", "/absolute/file.jpg"])
def test_model_source_traversal_or_absolute_path_aborts(
    tmp_path: Path, source: str
) -> None:
    artist, template = layout(tmp_path)

    def query(
        _endpoint: str,
        _model: str,
        _timeout: float,
        files: list[dict[str, Any]],
        _allowed: list[str],
    ) -> dict[str, Any]:
        response = response_for(files)
        response["items"][0]["source_relpath"] = source
        return response

    with pytest.raises(NORMALIZE.NormalizationError):
        build(artist, template, query)


@pytest.mark.parametrize("destination", ["../escape", "/absolute"])
def test_invalid_model_destination_falls_back_without_escaping(
    tmp_path: Path, destination: str
) -> None:
    artist, template = layout(tmp_path)

    def query(
        _endpoint: str,
        _model: str,
        _timeout: float,
        files: list[dict[str, Any]],
        _allowed: list[str],
    ) -> dict[str, Any]:
        response = response_for(files)
        response["items"][0]["destination_directory"] = destination
        return response

    plan = build(artist, template, query)
    assert plan["items"][0]["destination_relpath"].startswith("09_TEMP_IMPORT/")
    assert plan["items"][0]["status"] == "UNRESOLVED"


def test_symlink_in_temp_import_is_rejected(tmp_path: Path) -> None:
    artist, template = layout(tmp_path)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    (artist / "09_TEMP_IMPORT" / "link.jpg").symlink_to(outside)

    with pytest.raises(NORMALIZE.NormalizationError, match="symlink"):
        build(artist, template, lambda *_args: pytest.fail("must not call Ollama"))


def test_symlink_in_template_is_rejected(tmp_path: Path) -> None:
    artist, template = layout(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (template / "linked-category").symlink_to(outside, target_is_directory=True)

    with pytest.raises(NORMALIZE.NormalizationError, match="symlink"):
        build(artist, template, lambda *_args: pytest.fail("must not call Ollama"))


def test_files_outside_temp_import_are_not_inventoried(tmp_path: Path) -> None:
    artist, template = layout(tmp_path)
    (artist / "00_MASTER").mkdir()
    (artist / "00_MASTER" / "must-not-be-read.txt").write_text(
        "outside scope", encoding="utf-8"
    )
    seen: list[str] = []

    def query(
        _endpoint: str,
        _model: str,
        _timeout: float,
        files: list[dict[str, Any]],
        _allowed: list[str],
    ) -> dict[str, Any]:
        seen.extend(item["source_relpath"] for item in files)
        return response_for(files)

    plan = build(artist, template, query)
    assert "must-not-be-read.txt" not in "\n".join(seen)
    assert plan["summary"]["source_files"] == 2


def test_template_without_reserved_temp_import_is_rejected(tmp_path: Path) -> None:
    artist, template = layout(tmp_path)
    (template / "09_TEMP_IMPORT").rmdir()

    with pytest.raises(NORMALIZE.NormalizationError, match="template is missing"):
        build(artist, template, lambda *_args: pytest.fail("must not call Ollama"))


@pytest.mark.parametrize("missing", ["temp", "template"])
def test_missing_temp_import_or_template_is_rejected(
    tmp_path: Path, missing: str
) -> None:
    artist, template = layout(tmp_path)
    target = artist / "09_TEMP_IMPORT" if missing == "temp" else template
    for child in sorted(target.rglob("*"), reverse=True):
        if child.is_file():
            child.unlink()
        else:
            child.rmdir()
    target.rmdir()

    with pytest.raises(NORMALIZE.MigrationError):
        build(artist, template, lambda *_args: pytest.fail("must not call Ollama"))


def test_empty_temp_import_produces_empty_plan_without_ollama(tmp_path: Path) -> None:
    artist = tmp_path / "EMPTY_Artist"
    (artist / "09_TEMP_IMPORT").mkdir(parents=True)
    template = tmp_path / "template"
    (template / "09_TEMP_IMPORT").mkdir(parents=True)

    plan = build(
        artist,
        template,
        lambda *_args: pytest.fail("empty plan must not call Ollama"),
    )

    assert plan["items"] == []
    assert plan["summary"]["source_files"] == 0
    assert plan["safety"]["operations_applied"] == 0


def test_write_plan_outputs_only_json_and_markdown_and_preserves_artist(
    tmp_path: Path,
) -> None:
    artist, template = layout(tmp_path)
    before = snapshot(artist)
    template_before = snapshot(template)
    plan = build(
        artist,
        template,
        lambda _endpoint, _model, _timeout, files, _allowed: response_for(files),
    )

    output = NORMALIZE.write_plan(plan, tmp_path / "normalizations", run_id="RUN001")

    assert {path.name for path in output.iterdir()} == {
        "NORMALIZATION_PLAN.json",
        "NORMALIZATION_PLAN.md",
    }
    loaded = json.loads(
        (output / "NORMALIZATION_PLAN.json").read_text(encoding="utf-8")
    )
    markdown = (output / "NORMALIZATION_PLAN.md").read_text(encoding="utf-8")
    assert loaded == plan
    assert "**Mode:** PLAN_ONLY" in markdown
    assert "**Operations applied:** 0" in markdown
    assert "04_WORKS/01_IMAGES/a/IMG_5378.jpg" in markdown
    assert snapshot(artist) == before
    assert snapshot(template) == template_before


def test_final_plan_validation_rejects_duplicate_or_incoherent_destinations(
    tmp_path: Path,
) -> None:
    artist, template = layout(tmp_path)
    plan = build(
        artist,
        template,
        lambda _endpoint, _model, _timeout, files, _allowed: response_for(files),
    )
    plan["items"][1]["destination_relpath"] = plan["items"][0]["destination_relpath"]

    with pytest.raises(NORMALIZE.NormalizationError, match="duplicate"):
        NORMALIZE.validate_normalization_plan(plan)

    plan = build(
        artist,
        template,
        lambda _endpoint, _model, _timeout, files, _allowed: response_for(files),
    )
    plan["items"][0]["status"] = "UNRESOLVED"

    with pytest.raises(NORMALIZE.NormalizationError, match="UNRESOLVED"):
        NORMALIZE.validate_normalization_plan(plan)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:11434",
        "http://example.com:11434",
        "http://127.0.0.1:9999",
        "http://user@127.0.0.1:11434",
        "http://127.0.0.1:11434/api/chat",
    ],
)
def test_remote_or_noncanonical_endpoint_is_rejected(endpoint: str) -> None:
    with pytest.raises(NORMALIZE.NormalizationError):
        NORMALIZE.validate_runtime_options(endpoint, "qwen3:8b", 1, 1)


@pytest.mark.parametrize(
    "error", [TimeoutError("timeout"), urllib.error.URLError("connection refused")]
)
def test_timeout_or_connection_refusal_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.setattr(
        NORMALIZE,
        "open_loopback",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )
    with pytest.raises(
        NORMALIZE.NormalizationError, match="local Ollama request failed"
    ):
        NORMALIZE.query_ollama(
            NORMALIZE.DEFAULT_ENDPOINT,
            NORMALIZE.DEFAULT_MODEL,
            1,
            [{"source_relpath": "file.jpg", "size_bytes": 1, "extension": ".jpg"}],
            ["09_TEMP_IMPORT"],
        )


@pytest.mark.parametrize(
    "raw",
    [
        b"not-json",
        b"[]",
        b"{}",
        b'{"message":{"content":"not-json"}}',
        b"x" * (NORMALIZE.MAX_RESPONSE_BYTES + 1),
    ],
)
def test_malformed_or_oversized_ollama_envelope_is_rejected(raw: bytes) -> None:
    with pytest.raises(NORMALIZE.NormalizationError):
        NORMALIZE.decode_ollama_response(raw)


def test_ollama_protocol_is_local_nonstreaming_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    content = {
        "items": [
            {
                "source_relpath": "file.jpg",
                "destination_directory": "09_TEMP_IMPORT",
                "status": "UNRESOLVED",
                "confidence": "LOW",
                "reason": "unknown",
            }
        ]
    }

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return json.dumps({"message": {"content": json.dumps(content)}}).encode()

    def fake_open(request: Any, timeout: float) -> Response:
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(NORMALIZE, "open_loopback", fake_open)
    result = NORMALIZE.query_ollama(
        NORMALIZE.DEFAULT_ENDPOINT,
        NORMALIZE.DEFAULT_MODEL,
        3,
        [{"source_relpath": "file.jpg", "size_bytes": 1, "extension": ".jpg"}],
        ["09_TEMP_IMPORT"],
    )

    assert result == content
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["format"] == "json"
    assert captured["timeout"] == 3


def test_ollama_http_redirect_is_refused() -> None:
    request = NORMALIZE.urllib.request.Request("http://127.0.0.1:11434/api/chat")
    handler = NORMALIZE.RejectRedirects()
    with pytest.raises(urllib.error.HTTPError, match="redirect refused"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://example.com/api/chat",
        )


def test_main_writes_only_fixed_core_normalizations_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    artist, template = layout(tmp_path)
    fake_core = tmp_path / "core"
    fake_core.mkdir()
    monkeypatch.setenv("GMV_CORE_ROOT", str(fake_core))
    monkeypatch.setattr(
        NORMALIZE,
        "query_ollama",
        lambda _endpoint, _model, _timeout, files, _allowed: response_for(files),
    )

    assert NORMALIZE.main([str(artist), "--template", str(template)]) == 0

    output = Path(capsys.readouterr().out.strip())
    assert output.parent == fake_core / "area35-qa" / "normalizations"
    assert {path.name for path in output.iterdir()} == {
        "NORMALIZATION_PLAN.json",
        "NORMALIZATION_PLAN.md",
    }


def test_gmv_cli_routes_artist_normalize_plan_to_core_venv(tmp_path: Path) -> None:
    core = tmp_path / "core"
    (core / ".venv" / "bin").mkdir(parents=True)
    (core / "10_API").mkdir()
    python = core / ".venv" / "bin" / "python"
    python.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
    python.chmod(0o755)
    env = os.environ.copy()
    env["GMV_CORE_ROOT"] = str(core)

    result = subprocess.run(
        [str(ROOT / "11_CLI" / "gmv"), "artist-normalize-plan", "artist"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout.splitlines() == [
        str(core / "10_API" / "gmv_artist_normalize_plan.py"),
        "artist",
    ]
