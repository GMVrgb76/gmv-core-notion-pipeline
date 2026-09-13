"""Crawler preplan step 4: SourceConnector Protocol + EvidenceUnit contract."""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))
import gmv_crawler_contracts as contracts  # noqa: E402

VALID_HASH = "sha256:" + "a" * 64


def _evidence_kwargs(**overrides: object) -> dict:
    base = {
        "evidence_id": "EVID-000001",
        "source_id": "sha256:" + "b" * 64,
        "source_revision": "rev-1",
        "content_hash": VALID_HASH,
        "locator": "/Area35/Garibaldi/cv.pdf",
        "start_offset": 100,
        "end_offset": 250,
        "text": "Federico Garibaldi ha esposto a Riyadh nel 2025.",
        # Bare 64-char lowercase hex, no "sha256:" prefix -- matches the
        # one real precedent in this repo, gmv_evidence_pipeline.py:297
        # (hashlib.sha256(text.encode()).hexdigest()), not content_hash's
        # prefixed format. EvidenceUnit does not validate text_hash's
        # shape (see contracts.py docstring): the two fields are not
        # interchangeable and must not be assumed to share a format.
        "text_hash": "c" * 64,
        "extraction_method": "pdf_text_layer",
        "extraction_confidence": 0.92,
    }
    base.update(overrides)
    return base


def test_validate_content_hash_accepts_well_formed_value() -> None:
    assert contracts.validate_content_hash(VALID_HASH) == VALID_HASH


@pytest.mark.parametrize(
    "bad_hash",
    ["not-a-hash", "sha256:abc", "sha256:" + "A" * 64, "sha256:" + "g" * 64],
)
def test_validate_content_hash_rejects_malformed_values(bad_hash: str) -> None:
    with pytest.raises(ValueError):
        contracts.validate_content_hash(bad_hash)


def test_source_metadata_validates_content_hash_on_construction() -> None:
    with pytest.raises(ValueError):
        contracts.SourceMetadata(
            locator="/x",
            filename="x.pdf",
            extension="pdf",
            mime_type="application/pdf",
            size=1024,
            modified_at=datetime.now(UTC),
            remote_revision="rev-1",
            content_hash="not-a-hash",
        )

    metadata = contracts.SourceMetadata(
        locator="/x",
        filename="x.pdf",
        extension="pdf",
        mime_type="application/pdf",
        size=1024,
        modified_at=datetime.now(UTC),
        remote_revision="rev-1",
        content_hash=VALID_HASH,
    )
    assert metadata.content_hash == VALID_HASH


def test_source_connector_protocol_is_runtime_checkable_and_structural() -> None:
    class FakeConnector:
        def list(self):
            return []

        def metadata(self, locator):
            raise NotImplementedError

        def download(self, locator):
            raise NotImplementedError

        def revision(self, locator):
            raise NotImplementedError

        def content_hash(self, locator):
            raise NotImplementedError

    assert isinstance(FakeConnector(), contracts.SourceConnector)

    class IncompleteConnector:
        def list(self):
            return []

    assert not isinstance(IncompleteConnector(), contracts.SourceConnector)


def test_evidence_unit_accepts_well_formed_values() -> None:
    evidence = contracts.EvidenceUnit(**_evidence_kwargs())
    assert evidence.content_hash == VALID_HASH
    assert evidence.page is None
    assert evidence.section is None


def test_evidence_unit_page_and_section_are_optional_but_settable() -> None:
    evidence = contracts.EvidenceUnit(**_evidence_kwargs(page=3, section="BIOGRAFIA"))
    assert evidence.page == 3
    assert evidence.section == "BIOGRAFIA"


@pytest.mark.parametrize(
    "overrides",
    [
        {"evidence_id": ""},
        {"source_id": ""},
        {"locator": ""},
        {"content_hash": "not-a-hash"},
        {"text_hash": ""},
        {"text": ""},
        {"start_offset": -1},
        {"end_offset": 50, "start_offset": 100},
        {"extraction_method": ""},
        {"extraction_confidence": 1.5},
        {"extraction_confidence": -0.1},
        {"page": 0},
    ],
    ids=[
        "empty-evidence-id",
        "empty-source-id",
        "empty-locator",
        "malformed-content-hash",
        "empty-text-hash",
        "empty-text",
        "negative-start-offset",
        "end-before-start",
        "empty-extraction-method",
        "confidence-above-one",
        "confidence-below-zero",
        "page-zero",
    ],
)
def test_evidence_unit_rejects_invalid_values(overrides: dict) -> None:
    with pytest.raises(ValueError):
        contracts.EvidenceUnit(**_evidence_kwargs(**overrides))


def test_evidence_unit_is_frozen() -> None:
    evidence = contracts.EvidenceUnit(**_evidence_kwargs())
    with pytest.raises(AttributeError):
        evidence.text = "mutated"


def test_evidence_unit_content_hash_format_matches_migration_009_check_constraint(
    tmp_path: Path,
) -> None:
    """Executes the real, fully-migrated crawler_source_registry table
    (built through gmv_core.migrations.migrate(), the same path
    production code uses -- not a hand-sliced fragment of the SQL file)
    and compares its verdict to validate_content_hash() for the same
    inputs, including the exact case a prior review found where they had
    already diverged (GLOB '[0-9a-f]' unrepeated constrains only one
    character position in SQLite, not a 64-character run) -- comparing
    pattern strings/lengths, as an earlier version of this test did,
    would not have caught that."""
    import sqlite3

    import gmv_core.migrations as migrations

    database = tmp_path / "content-hash-check.db"
    migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)

    candidates = [
        VALID_HASH,
        "not-a-hash",
        "sha256:abc",
        "sha256:" + "a" * 63,
        "sha256:" + "A" * 64,
        "sha256:" + "g" * 64,
        "sha256:a" + "A" * 63,
    ]

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for candidate in candidates:
            try:
                connection.execute(
                    """
                    INSERT INTO crawler_source_registry
                        (content_hash, connector, canonical_locator, discovered_at, last_seen_at)
                    VALUES (?, 'dropbox', '/x', 't', 't')
                    """,
                    (candidate,),
                )
                sql_accepts = True
            except sqlite3.IntegrityError:
                sql_accepts = False
            connection.execute("DELETE FROM crawler_source_registry")

            try:
                contracts.validate_content_hash(candidate)
                python_accepts = True
            except ValueError:
                python_accepts = False

            assert sql_accepts == python_accepts, (
                f"{candidate!r}: SQL CHECK accepts={sql_accepts}, "
                f"Python validator accepts={python_accepts} -- diverged"
            )
