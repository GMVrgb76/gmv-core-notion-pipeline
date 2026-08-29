from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "10_API"
sys.path.insert(0, str(API_ROOT))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "10_API" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PLAN = load("gmv_artist_migrate_plan")
APPLY = load("gmv_artist_migrate_apply")


def report_for(source: Path, paths: list[str]) -> str:
    rows = "\n".join(
        f"| F{index:04d} | {Path(value).name} | .txt | 1 B | YES | NOT CHECKED | {value} |"
        for index, value in enumerate(paths, 1)
    )
    return (
        "# GMV Folder Report\n\n"
        f"**Source:** `{source}`  \n"
        f"**Files successfully inventoried:** {len(paths)}  \n\n"
        "## Summary index\n\n"
        "| ID | File | Type | Size | Text/Info | GMV Master | Path |\n"
        "|---|---|---|---:|---|---|---|\n"
        f"{rows}\n\n## Scan evidence\n\nSource scan complete: **YES**\n"
    )


def test_plan_then_apply_moves_only_declared_files_and_directories(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    template = tmp_path / "template"
    destination_root = tmp_path / "artists"
    (source / "nested").mkdir(parents=True)
    template.mkdir()
    (template / "09_TEMP_IMPORT").mkdir()
    (template / "README.md").write_text("not copied", encoding="utf-8")
    (source / "one.txt").write_text("one", encoding="utf-8")
    (source / "nested" / "two.txt").write_text("two", encoding="utf-8")
    destination_root.mkdir()
    report = tmp_path / "report.md"
    report.write_text(
        report_for(source, ["one.txt", "nested/two.txt"]), encoding="utf-8"
    )
    plan = PLAN.build_plan(source, report, template, "TEST_Artist", destination_root)
    plan_path = tmp_path / "TEST_Artist_MIGRATION_PLAN.yaml"
    PLAN.yaml_write(plan_path, plan)

    result = APPLY.apply_plan(plan_path, input_fn=lambda _: "y")

    artist = destination_root / "TEST_Artist"
    assert result["status"] == "COMPLETED"
    assert result["moved_item_count"] == 2
    assert not (source / "one.txt").exists()
    assert (artist / "09_TEMP_IMPORT" / "one.txt").read_text() == "one"
    assert (artist / "09_TEMP_IMPORT" / "nested" / "two.txt").read_text() == "two"
    assert not (artist / "README.md").exists()
    assert (tmp_path / "TEST_Artist_MIGRATION_RESULT.json").is_file()


@pytest.mark.parametrize("filename", ["IMG_5378.jpg", "0001.jpg"])
def test_duplicate_basenames_preserve_source_paths_and_apply(
    tmp_path: Path, filename: str
) -> None:
    source = tmp_path / "source"
    template = tmp_path / "template"
    destination_root = tmp_path / "artists"
    (source / "a").mkdir(parents=True)
    (source / "b").mkdir()
    (source / "a" / filename).write_bytes(b"from-a")
    (source / "b" / filename).write_bytes(b"from-b")
    (template / "09_TEMP_IMPORT").mkdir(parents=True)
    destination_root.mkdir()
    report = tmp_path / "report.md"
    report.write_text(
        report_for(source, [f"a/{filename}", f"b/{filename}"]), encoding="utf-8"
    )

    plan = PLAN.build_plan(source, report, template, "TEST_Artist", destination_root)
    assert [item["source_relpath"] for item in plan["items"]] == [
        f"a/{filename}",
        f"b/{filename}",
    ]
    assert [item["destination_relpath"] for item in plan["items"]] == [
        f"09_TEMP_IMPORT/a/{filename}",
        f"09_TEMP_IMPORT/b/{filename}",
    ]
    assert all(
        Path(item["destination_relpath"]).name == filename for item in plan["items"]
    )
    plan_path = tmp_path / "plan.yaml"
    PLAN.yaml_write(plan_path, plan)

    result = APPLY.apply_plan(plan_path, input_fn=lambda _: "y")

    artist = destination_root / "TEST_Artist" / "09_TEMP_IMPORT"
    assert result["status"] == "COMPLETED"
    assert (artist / "a" / filename).read_bytes() == b"from-a"
    assert (artist / "b" / filename).read_bytes() == b"from-b"
    assert not (source / "a" / filename).exists()
    assert not (source / "b" / filename).exists()


def test_plan_rejects_true_duplicate_source_and_moves_nothing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    template = tmp_path / "template"
    destination_root = tmp_path / "artists"
    source.mkdir()
    template.mkdir()
    destination_root.mkdir()
    (source / "same.jpg").write_bytes(b"unchanged")
    report = tmp_path / "report.md"
    report.write_text(report_for(source, ["same.jpg", "same.jpg"]), encoding="utf-8")

    with pytest.raises(PLAN.MigrationError, match="duplicate IDs or source paths"):
        PLAN.build_plan(source, report, template, "TEST_Artist", destination_root)

    assert (source / "same.jpg").read_bytes() == b"unchanged"
    assert not (destination_root / "TEST_Artist").exists()


def test_plan_validation_rejects_true_duplicate_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    template = tmp_path / "template"
    destination_root = tmp_path / "artists"
    (source / "a").mkdir(parents=True)
    (source / "b").mkdir()
    template.mkdir()
    destination_root.mkdir()
    report = tmp_path / "report.md"
    report.write_text(report_for(source, ["a/one.jpg", "b/two.jpg"]), encoding="utf-8")
    plan = PLAN.build_plan(source, report, template, "TEST_Artist", destination_root)
    plan["items"][1]["destination_relpath"] = plan["items"][0]["destination_relpath"]

    with pytest.raises(
        PLAN.MigrationError, match="duplicate ID, source, or destination"
    ):
        PLAN.validate_plan(plan)

    assert not (destination_root / "TEST_Artist").exists()


def test_apply_declines_by_default_without_creating_artist_folder(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    template = tmp_path / "template"
    destination_root = tmp_path / "artists"
    source.mkdir()
    template.mkdir()
    destination_root.mkdir()
    (source / "one.txt").write_text("one", encoding="utf-8")
    report = tmp_path / "report.md"
    report.write_text(report_for(source, ["one.txt"]), encoding="utf-8")
    plan = PLAN.build_plan(source, report, template, "TEST_Artist", destination_root)
    plan_path = tmp_path / "plan.yaml"
    PLAN.yaml_write(plan_path, plan)
    with pytest.raises(APPLY.MigrationError, match="cancelled"):
        APPLY.apply_plan(plan_path, input_fn=lambda _: "")
    assert (source / "one.txt").is_file()
    assert not (destination_root / "TEST_Artist").exists()
