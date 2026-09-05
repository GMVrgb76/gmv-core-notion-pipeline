import importlib.util
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("evidence", Path(__file__).parents[1] / "10_API" / "gmv_evidence_pipeline.py")
evidence = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(evidence)
sys.path.insert(0, str(Path(__file__).parents[1] / "10_API"))
import pipeline_status

FIXTURES = Path(__file__).parent / "fixtures"


def _make_evidence_root(evidence_root: Path, files: dict[str, bytes]) -> None:
    source = evidence_root / "_source"; source.mkdir(parents=True)
    for name, content in files.items():
        (source / name).write_bytes(content)
    evidence.scan(source, evidence_root)
    evidence.extract(evidence_root, source)


def test_pipeline_results_when_no_evidence_roots_dir(tmp_path):
    results = pipeline_status.pipeline_results(tmp_path / "does_not_exist")
    assert len(results) == 1
    assert results[0].name == "pipeline.evidence"
    assert results[0].status == "PASS"
    assert "not been executed yet" in results[0].message


def test_pipeline_results_all_success(tmp_path):
    roots_dir = tmp_path / "evidence"
    _make_evidence_root(roots_dir / "garibaldi", {"bio.txt": b"Federico Garibaldi"})
    results = pipeline_status.pipeline_results(roots_dir)
    assert len(results) == 1
    assert results[0].status == "PASS"
    assert "1 artist(s), 1 file(s) scanned" in results[0].message
    assert "0 needing attention" in results[0].message


def test_pipeline_results_flags_needs_attention(tmp_path):
    roots_dir = tmp_path / "evidence"
    _make_evidence_root(roots_dir / "garibaldi", {
        "bio.txt": b"Federico Garibaldi",
        "bad.pdf": (FIXTURES / "corrupt.pdf").read_bytes(),
    })
    results = pipeline_status.pipeline_results(roots_dir)
    names = {r.name: r for r in results}
    assert names["pipeline.evidence"].status == "DEGRADED"
    assert "1 needing attention" in names["pipeline.evidence"].message
    per_artist = names["pipeline.evidence.garibaldi"]
    assert per_artist.status == "DEGRADED"
    assert "EXTRACTION_FAILED=1" in per_artist.message


def test_pipeline_results_multiple_artists_aggregate(tmp_path):
    roots_dir = tmp_path / "evidence"
    _make_evidence_root(roots_dir / "garibaldi", {"bio.txt": b"Federico Garibaldi"})
    _make_evidence_root(roots_dir / "morales", {"bio.txt": b"Ernesto Morales", "cv.txt": b"CV"})
    results = pipeline_status.pipeline_results(roots_dir)
    assert len(results) == 1
    assert "2 artist(s), 3 file(s) scanned" in results[0].message


def test_discover_evidence_roots_ignores_non_evidence_subdirs(tmp_path):
    roots_dir = tmp_path / "evidence"
    roots_dir.mkdir()
    (roots_dir / "not_an_evidence_root").mkdir()
    (roots_dir / "some_file.txt").write_text("x", encoding="utf-8")
    _make_evidence_root(roots_dir / "garibaldi", {"bio.txt": b"Federico Garibaldi"})
    found = pipeline_status.discover_evidence_roots(roots_dir)
    assert [p.name for p in found] == ["garibaldi"]
