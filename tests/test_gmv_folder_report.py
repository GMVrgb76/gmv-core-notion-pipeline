from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "10_API" / "gmv_folder_report.py"
SPEC = importlib.util.spec_from_file_location("gmv_folder_report", SCRIPT)
assert SPEC and SPEC.loader
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def test_report_excludes_its_output_and_does_not_follow_symlinks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "note.md").write_text("alpha", encoding="utf-8")
    nested = source / "nested"
    nested.mkdir()
    (nested / "loop").symlink_to(source, target_is_directory=True)
    output = source / "report.md"

    REPORT.report_folder(source, None, output)
    REPORT.report_folder(source, None, output)
    text = output.read_text(encoding="utf-8")

    assert "**Files successfully inventoried:** 1" in text
    assert "loop@ ->" in text
    assert "symlink directory skipped" in text
    assert "### F0001 — note\\.md" in text
    assert "### F0002" not in text


def test_exact_master_match_and_duplicate_detection(tmp_path: Path) -> None:
    source = tmp_path / "source"
    master = tmp_path / "master"
    source.mkdir()
    master.mkdir()
    (source / "one.txt").write_text("same", encoding="utf-8")
    (source / "two.txt").write_text("same", encoding="utf-8")
    (master / "canonical.txt").write_text("same", encoding="utf-8")
    output = tmp_path / "report.md"

    REPORT.report_folder(source, master, output)
    text = output.read_text(encoding="utf-8")

    assert "Exact file matches: **2**" in text
    assert "Master index complete: **YES**" in text
    assert "one.txt" in text and "two.txt" in text
    assert "canonical.txt" in text


def test_recursive_inventory_covers_nested_files_everywhere(tmp_path: Path) -> None:
    source = tmp_path / "source"
    nested = source / "fotomostra fabio" / "jpg x Giacomo"
    nested.mkdir(parents=True)
    master = tmp_path / "master"
    master.mkdir()
    (source / "root.txt").write_text("duplicate", encoding="utf-8")
    (nested / "nested.txt").write_text("duplicate", encoding="utf-8")
    (master / "canonical.txt").write_text("duplicate", encoding="utf-8")
    output = tmp_path / "report.md"

    REPORT.report_folder(source, master, output)
    text = output.read_text(encoding="utf-8")

    assert "**Files successfully inventoried:** 2" in text
    assert "fotomostra fabio/jpg x Giacomo/nested.txt" in text
    assert "Exact file matches: **2**" in text
    assert "### F0001 — nested\\.txt" in text
    assert "### F0002 — root\\.txt" in text
    assert "No exact duplicates detected." not in text


def test_version_is_v011(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        REPORT.parse_args(["--version"])
    assert exit_info.value.code == 0
    assert "0.1.1" in capsys.readouterr().out


def test_markdown_content_cannot_close_preview_fence(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "odd`name.md").write_text("before ``` after", encoding="utf-8")
    output = tmp_path / "report.md"

    REPORT.report_folder(source, None, output)
    text = output.read_text(encoding="utf-8")

    assert "````text\nbefore ``` after\n````" in text
    assert "odd`name.md" in text


def test_rejects_same_source_and_master(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="devono essere cartelle diverse"):
        REPORT.main([str(tmp_path), "--master", str(tmp_path)])


def test_cli_folder_report_honors_core_root_override(tmp_path: Path) -> None:
    core = tmp_path / "core"
    (core / ".venv" / "bin").mkdir(parents=True)
    (core / "10_API").mkdir()
    python = core / ".venv" / "bin" / "python"
    python.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
    python.chmod(0o755)
    env = os.environ.copy()
    env["GMV_CORE_ROOT"] = str(core)

    result = subprocess.run(
        [str(ROOT / "11_CLI" / "gmv"), "folder-report", "source", "--master", "master"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout.splitlines() == [
        str(core / "10_API" / "gmv_folder_report.py"),
        "source",
        "--master",
        "master",
    ]
