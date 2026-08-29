from __future__ import annotations

import builtins
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
SPEC = importlib.util.spec_from_file_location(
    "gmv_artist_import", ROOT / "10_API" / "gmv_artist_import.py"
)
assert SPEC and SPEC.loader
IMPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORT)


def paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source, template, artists, qa = (
        tmp_path / "Ada Rossi",
        tmp_path / "template",
        tmp_path / "artists",
        tmp_path / "qa",
    )
    (source / "nested").mkdir(parents=True)
    (source / "one.jpg").write_bytes(b"one")
    (source / "nested" / "two.pdf").write_bytes(b"two")
    (template / "09_TEMP_IMPORT").mkdir(parents=True)
    (template / "00_MASTER").mkdir()
    (template / "README.md").write_text("not copied", encoding="utf-8")
    artists.mkdir()
    return source, template, artists, qa


def args(source: Path, template: Path, artists: Path, qa: Path) -> list[str]:
    return [
        str(source),
        "--template",
        str(template),
        "--destination-root",
        str(artists),
        "--qa-root",
        str(qa),
    ]


def accept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins, "input", lambda _prompt: "y")


def latest_run(qa: Path) -> Path:
    return next((qa / "imports").iterdir())


def test_user_abort_has_no_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, template, artists, qa = paths(tmp_path)
    monkeypatch.setattr(builtins, "input", lambda _prompt: "")
    assert IMPORT.main(args(source, template, artists, qa)) == 2
    assert len(IMPORT.regular_files(source)) == 2
    assert not (artists / "ROSSI_Ada").exists()
    assert not qa.exists()


def test_successful_end_to_end_writes_only_run_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, template, artists, qa = paths(tmp_path)
    accept(monkeypatch)
    assert IMPORT.main(args(source, template, artists, qa)) == 0
    run = latest_run(qa)
    assert {path.name for path in run.iterdir()} == {
        "SOURCE_REPORT.md",
        "PRE_MIGRATION_HASHES.json",
        "MIGRATION_PLAN.yaml",
        "MIGRATION_PLAN.md",
        "MIGRATION_RESULT.json",
        "MIGRATION_RESULT.md",
        "IMPORT_REPORT.md",
    }
    assert len(IMPORT.regular_files(source)) == 0
    assert (artists / "ROSSI_Ada" / "09_TEMP_IMPORT" / "one.jpg").read_bytes() == b"one"
    assert (
        artists / "ROSSI_Ada" / "09_TEMP_IMPORT" / "nested" / "two.pdf"
    ).read_bytes() == b"two"
    assert "**Status:** COMPLETED" in (run / "IMPORT_REPORT.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("filename", ["IMG_5378.jpg", "0001.jpg"])
def test_orchestrator_verifies_recursive_temp_import_destinations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str
) -> None:
    source = tmp_path / "Gaspare Manos"
    template = tmp_path / "template"
    artists = tmp_path / "artists"
    qa = tmp_path / "qa"
    (source / "a").mkdir(parents=True)
    (source / "b").mkdir()
    (source / "a" / filename).write_bytes(b"from-a")
    (source / "b" / filename).write_bytes(b"from-b")
    (template / "09_TEMP_IMPORT").mkdir(parents=True)
    artists.mkdir()
    accept(monkeypatch)

    assert IMPORT.main(args(source, template, artists, qa)) == 0

    run = latest_run(qa)
    plan = yaml.safe_load((run / "MIGRATION_PLAN.yaml").read_text(encoding="utf-8"))
    assert [item["destination_relpath"] for item in plan["items"]] == [
        f"09_TEMP_IMPORT/a/{filename}",
        f"09_TEMP_IMPORT/b/{filename}",
    ]
    destination = artists / "MANOS_Gaspare" / "09_TEMP_IMPORT"
    assert (destination / "a" / filename).read_bytes() == b"from-a"
    assert (destination / "b" / filename).read_bytes() == b"from-b"
    report = (run / "IMPORT_REPORT.md").read_text(encoding="utf-8")
    assert "SHA-256 verified: 2/2" in report
    assert "**Status:** COMPLETED" in report


def test_folder_report_failure_is_aborted_without_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, template, artists, qa = paths(tmp_path)
    accept(monkeypatch)
    original = IMPORT.run
    monkeypatch.setattr(
        IMPORT,
        "run",
        lambda command, **kwargs: (
            subprocess.CompletedProcess(command, 1, "", "folder failure")
            if Path(command[1]) == IMPORT.FOLDER_REPORT
            else original(command, **kwargs)
        ),
    )
    assert IMPORT.main(args(source, template, artists, qa)) == 1
    assert not (artists / "ROSSI_Ada").exists()
    assert "**Status:** ABORTED" in (latest_run(qa) / "IMPORT_REPORT.md").read_text(
        encoding="utf-8"
    )


def test_plan_failure_is_aborted_without_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, template, artists, qa = paths(tmp_path)
    accept(monkeypatch)
    original = IMPORT.run
    monkeypatch.setattr(
        IMPORT,
        "run",
        lambda command, **kwargs: (
            subprocess.CompletedProcess(command, 1, "", "plan failure")
            if Path(command[1]) == IMPORT.MIGRATE_PLAN
            else original(command, **kwargs)
        ),
    )
    assert IMPORT.main(args(source, template, artists, qa)) == 1
    assert len(IMPORT.regular_files(source)) == 2
    assert not (artists / "ROSSI_Ada").exists()


def test_apply_partial_is_reported_as_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, template, artists, qa = paths(tmp_path)
    accept(monkeypatch)
    original = IMPORT.run

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if Path(command[1]) != IMPORT.MIGRATE_APPLY:
            return original(command, **kwargs)
        base = Path(command[command.index("--result-output") + 1])
        base.with_suffix(".json").write_text(
            json.dumps(
                {"status": "PARTIAL", "moved_item_count": 1, "failed_item_count": 1}
            ),
            encoding="utf-8",
        )
        base.with_suffix(".md").write_text("partial", encoding="utf-8")
        return subprocess.CompletedProcess(command, 1, "", "simulated apply failure")

    monkeypatch.setattr(IMPORT, "run", fake_run)
    assert IMPORT.main(args(source, template, artists, qa)) == 1
    assert "**Status:** PARTIAL" in (latest_run(qa) / "IMPORT_REPORT.md").read_text(
        encoding="utf-8"
    )


def test_existing_destination_fails_before_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, template, artists, qa = paths(tmp_path)
    (artists / "ROSSI_Ada").mkdir()
    monkeypatch.setattr(
        builtins, "input", lambda _prompt: pytest.fail("must not confirm")
    )
    with pytest.raises(SystemExit):
        IMPORT.main(args(source, template, artists, qa))
    assert len(IMPORT.regular_files(source)) == 2
    assert not qa.exists()


def test_hash_mismatch_is_not_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, template, artists, qa = paths(tmp_path)
    accept(monkeypatch)
    original = IMPORT.sha256
    destination = artists / "ROSSI_Ada"
    monkeypatch.setattr(
        IMPORT,
        "sha256",
        lambda path: "0" * 64 if destination in path.parents else original(path),
    )
    assert IMPORT.main(args(source, template, artists, qa)) == 1
    report = (latest_run(qa) / "IMPORT_REPORT.md").read_text(encoding="utf-8")
    assert "**Status:** PARTIAL" in report
    assert "SHA-256 verified: 0/2" in report
