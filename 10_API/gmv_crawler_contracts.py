#!/usr/bin/env python3
"""GMV Crawler — Source and Evidence contracts (crawler preplan step 4).

Two contracts, nothing else. `SourceConnector` is the abstract interface
any ingestion source (Dropbox today, filesystem/email/Google Drive later)
must implement -- the crawler engine never talks to a specific source
directly, only to this contract. `EvidenceUnit` is the provenance record
that closes the gap the frozen GMV_KNOWLEDGE_MONAD_SPEC_v1.0 leaves open:
ATOM -> SOURCE_ID exists, but nothing says which exact page/passage/
revision produced the proposition until this unit exists.

No concrete connector is implemented here. gmv-dropbox-import, assumed by
an earlier draft of the crawler spec to be an already-validated wrapper
target, does not exist as code anywhere in this repository or its
history -- it is a Claude Skill (an LLM-guided manual folder-reorg
workflow), not a deterministic list/metadata/download/content_hash API.
A real Dropbox connector implementing this contract is future work, not
assumed solved by this file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

CONTENT_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def validate_content_hash(value: str) -> str:
    """Enforce the same sha256:<hex> identity format as
    crawler_source_registry.content_hash (gmv_core/migration_sql/
    009_crawler_source_registry.sql) -- one format, not two definitions
    that could silently drift apart between the DB layer and this
    contract layer."""
    if not CONTENT_HASH_PATTERN.match(value):
        raise ValueError(
            f"content_hash must match sha256:<64 lowercase hex chars>, got: {value!r}"
        )
    return value


@dataclass(frozen=True, slots=True)
class SourceListing:
    """One entry from SourceConnector.list() -- cheap enumeration only.
    No content_hash here: computing it may require a network call
    (metadata() or download()) a connector should not pay during a
    plain listing pass."""

    locator: str
    filename: str
    size: int
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    """The richer per-item record SourceConnector.metadata() returns.
    content_hash is validated to the same format the Core persistence
    layer enforces, so a connector cannot hand the crawler an identity
    the registry would reject."""

    locator: str
    filename: str
    extension: str
    mime_type: str
    size: int
    modified_at: datetime
    remote_revision: str
    content_hash: str

    def __post_init__(self) -> None:
        validate_content_hash(self.content_hash)


@runtime_checkable
class SourceConnector(Protocol):
    """Structural contract every ingestion source must satisfy. The
    crawler engine depends only on this Protocol -- never on a specific
    connector's implementation details. No inheritance is required
    (Protocol, not ABC) -- this repository has no existing precedent
    either way for defining a multi-method contract (grep for
    abc.ABC/@abstractmethod/typing.Protocol returns nothing outside this
    file; gmv_core/repositories/*.py exposes free functions taking a
    sqlite3.Connection, not an interface object), so this is a first
    choice, not a continuation of an established pattern.

    @runtime_checkable makes isinstance() check that a class defines
    these five method names -- it does not check parameter or return
    type signatures. Only a static type checker (mypy/pyright) verifies
    that.
    """

    def list(self) -> list[SourceListing]:
        """Enumerate everything currently visible in this source's scope."""
        ...

    def metadata(self, locator: str) -> SourceMetadata:
        """Fetch the full per-item record for one locator."""
        ...

    def download(self, locator: str) -> bytes:
        """Fetch raw content bytes for one locator."""
        ...

    def revision(self, locator: str) -> str:
        """Return the connector-native revision/version marker for one
        locator. Independent of content_hash: some sources version
        identical content (e.g. a no-op save), which must not be
        confused with the file actually changing."""
        ...

    def content_hash(self, locator: str) -> str:
        """Return this locator's content identity as sha256:<64 hex
        chars>. This is the crawler's canonical identity criterion
        (Correction 6: content-hash-first, not path or filename) -- the
        same value that becomes crawler_source_registry.content_hash."""
        ...


@dataclass(frozen=True, slots=True)
class EvidenceUnit:
    """The provenance record closing the gap GMV_KNOWLEDGE_MONAD_SPEC_v1.0
    leaves open: ATOM -> SOURCE_ID exists in the frozen schema, but no
    addressable object says which exact page/passage/revision produced
    the proposition. Schema is exactly the field list from the crawler
    spec §8, no field added or removed.

    page/section are optional by design, not an oversight: a plain TXT
    or MD source has no page concept, and asserting one where the source
    format does not support it would itself violate Epistemic Ingestion
    Rule EIC-03 (a document assertion is not automatically a real-world
    fact) applied one level down, to the shape of the evidence itself.

    source_id and content_hash: in the content-hash-first identity model
    (Correction 6), these are expected to hold the same sha256:<hex>
    value in the common case -- source_id names which
    crawler_source_registry row this evidence came from, content_hash is
    that row's identity at extraction time. Kept as two separate fields,
    not one, so an EvidenceUnit stays a self-contained, independently
    auditable provenance record even if the registry row it points to is
    later modified or removed -- not because the two are expected to
    diverge today.

    text_hash is deliberately NOT format-validated the way content_hash
    is: the one real precedent for this field in this repository
    (gmv_evidence_pipeline.py:297, hashlib.sha256(text.encode()).
    hexdigest()) produces bare 64-char lowercase hex with no "sha256:"
    prefix -- a different shape from content_hash's prefixed form. This
    field's exact contract is intentionally left open until a real
    consumer forces the decision, rather than guessed at here.
    """

    evidence_id: str
    source_id: str
    source_revision: str
    content_hash: str
    locator: str
    start_offset: int
    end_offset: int
    text: str
    text_hash: str
    extraction_method: str
    extraction_confidence: float
    page: int | None = None
    section: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ValueError("evidence_id must not be empty")
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        if not self.locator:
            raise ValueError(
                "locator must not be empty -- an EvidenceUnit with no canonical "
                "locator violates the crawler's foundational invariant "
                "(no SOURCE without canonical locator)"
            )
        validate_content_hash(self.content_hash)
        if not self.text_hash:
            raise ValueError("text_hash must not be empty")
        if not self.text:
            raise ValueError("text must not be empty")
        if self.start_offset < 0:
            raise ValueError(f"start_offset must be >= 0, got {self.start_offset}")
        if self.end_offset < self.start_offset:
            raise ValueError(
                f"end_offset ({self.end_offset}) must be >= start_offset "
                f"({self.start_offset})"
            )
        if not self.extraction_method:
            raise ValueError("extraction_method must not be empty")
        if not (0.0 <= self.extraction_confidence <= 1.0):
            raise ValueError(
                f"extraction_confidence must be in [0.0, 1.0], got "
                f"{self.extraction_confidence}"
            )
        if self.page is not None and self.page < 1:
            raise ValueError(f"page must be >= 1 when present, got {self.page}")
