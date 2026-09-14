#!/usr/bin/env python3
"""GMV Crawler — Dropbox SourceConnector (crawler preplan step 9).

A real HTTP client against the Dropbox API v2 (RPC endpoints on
api.dropboxapi.com, the content endpoint on content.dropboxapi.com),
implementing the `SourceConnector` Protocol from `gmv_crawler_contracts.py`
(step 4) structurally (duck-typed, no inheritance — see that module's own
docstring for why this repo uses `typing.Protocol` here).

GMV_CRAWLER_HANDOFF.md's Correction 2 still applies: this is *not* a
wrapper of the `gmv-dropbox-import` Skill (an LLM-guided manual
AUDIT/ESECUZIONE/NORMALIZZAZIONE workflow with a human-confirmation step —
verified in two prior sessions to be a Claude Skill file, not code). This
module is a from-scratch, deterministic client against Dropbox's own
list_folder / get_metadata / download endpoints, per the user's explicit
choice between the two ways to unblock step 9.

Authentication: a single static access token, read from the
DROPBOX_ACCESS_TOKEN environment variable (or passed explicitly) — the
user's explicit choice among the options offered (vs. an OAuth2
refresh-token flow). Token resolution reuses `credentials.get_token()`
(repo root) rather than reading `os.environ` directly: that helper is
already the repo's one generic, centralized env-var-then-explicit-error
token resolver (its docstring frames it as Notion-specific, but its
signature -- `get_token(name, file_fallback=None)` -- takes the env var
name as a parameter and has no Notion-specific logic; it is already
consumed by six files). Adding a second, ad-hoc `os.environ.get()` read
here would have been undeclared duplication of an established pattern
this session's own working method explicitly warns against. If the token
expires or is revoked, every method here raises `DropboxConnectorError`
from a 401 response, or from `credentials.TokenError` at construction
time if no token is configured at all -- there is no automatic refresh.
Network-layer failures (timeout, DNS, connection reset --
`requests.exceptions.RequestException` and subclasses) are also
normalized to `DropboxConnectorError`, not left to propagate raw.

content_hash() deliberately does NOT reuse Dropbox's own `content_hash`
metadata field, even though that field is also a 64-hex-char string that
would satisfy `CONTENT_HASH_PATTERN`'s format. Dropbox's `content_hash` is
a custom blockwise algorithm (SHA-256 of the concatenation of per-4MB-block
SHA-256 hashes — see Dropbox's own "Content hash" documentation), not a
plain single-pass SHA-256 of the file's bytes. Every other content_hash
producer in this repo (`gmv_evidence_pipeline.py:297` computes it
directly; `gmv_core/repositories/resources.py` persists a value computed
the same way by `import_service.sha256_file()`) traces back to
`hashlib.sha256(bytes).hexdigest()`. Since the crawler's whole identity
model (spec Correction 6, content-hash-first) depends on the *same
physical bytes producing the same content_hash regardless of which source
saw them*, silently reusing Dropbox's own differently-computed hash would
plant a hash that matches the sha256:<hex> format but is not comparable to
every other producer's value — a real, silent correctness bug for
cross-source dedup, not just a cosmetic mismatch. This connector instead
downloads the file and computes a real SHA-256, at the cost of making
content_hash() (and metadata(), which calls it) a full-download operation
rather than a cheap metadata-only call. That cost is deliberate and
documented here, not hidden. Also undocumented-until-now here: both
`download()` and `content_hash()` hold the entire file in memory at once
(`response.content`, then a single `hashlib.sha256(payload)` call) rather
than streaming in chunks the way `gmv_evidence_pipeline.sha256_file()`/
`import_service.sha256_file()` do for local files -- fine for typical
document-sized evidence, but a real memory-scaling limit for very large
files that a future step should address (`requests`' `stream=True` plus
chunked `hashlib.update()`) if the crawler ever needs to ingest large
media, not just documents.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from credentials import TokenError, get_token  # noqa: E402 -- reused, not reimplemented
from gmv_crawler_contracts import SourceListing, SourceMetadata  # noqa: E402 -- reused, not reimplemented

RPC_BASE_URL = "https://api.dropboxapi.com/2"
CONTENT_BASE_URL = "https://content.dropboxapi.com/2"
DEFAULT_TIMEOUT_SECONDS = 30.0
TOKEN_ENV_VAR = "DROPBOX_ACCESS_TOKEN"  # noqa: S105 (env var name, not a secret value)


class DropboxConnectorError(RuntimeError):
    """Raised on any Dropbox API failure: missing/invalid token, a locator
    that does not exist or is not a file, or a non-200 HTTP response."""


class DropboxConnector:
    """SourceConnector (see gmv_crawler_contracts.SourceConnector) against
    the real Dropbox API v2, scoped to one folder subtree.

    `session` is injectable (defaults to a fresh `requests.Session()`) so
    tests can supply a fake with a `.post()` method instead of making real
    network calls — no new test dependency needed, this repo has no
    HTTP-mocking library and `requests` itself is already the one real
    dependency this module needs.
    """

    def __init__(
        self,
        *,
        root_path: str = "",
        access_token: str | None = None,
        session: requests.Session | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if access_token:
            self._token = access_token
        else:
            try:
                self._token = get_token(TOKEN_ENV_VAR).value
            except TokenError as exc:
                raise DropboxConnectorError(
                    "no Dropbox access token: pass access_token= explicitly or "
                    f"set the {TOKEN_ENV_VAR} environment variable"
                ) from exc
        self._root_path = root_path
        self._session = session if session is not None else requests.Session()
        self._timeout = timeout

    def _headers(self, **extra: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", **extra}

    def _rpc(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._session.post(
                f"{RPC_BASE_URL}/{endpoint}",
                headers=self._headers(**{"Content-Type": "application/json"}),
                json=payload,
                timeout=self._timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise DropboxConnectorError(f"Dropbox API {endpoint} request failed: {exc}") from exc
        if response.status_code != 200:
            raise DropboxConnectorError(
                f"Dropbox API {endpoint} failed: HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
        return response.json()

    def list(self) -> list[SourceListing]:
        """Enumerate every file (not folder, not deleted) under root_path,
        recursively, following list_folder/continue pagination."""
        result = self._rpc(
            "files/list_folder",
            {"path": self._root_path, "recursive": True, "include_deleted": False},
        )
        entries: list[dict[str, Any]] = list(result["entries"])
        while result.get("has_more"):
            result = self._rpc("files/list_folder/continue", {"cursor": result["cursor"]})
            entries.extend(result["entries"])
        return [
            SourceListing(
                locator=entry["path_lower"],
                filename=entry["name"],
                size=entry["size"],
                modified_at=_parse_dropbox_timestamp(entry["server_modified"]),
            )
            for entry in entries
            if entry.get(".tag") == "file"
        ]

    def metadata(self, locator: str) -> SourceMetadata:
        """Full per-item record. Downloads the file to compute a real
        SHA-256 content_hash (see module docstring) — not a cheap call."""
        entry = self._get_file_entry(locator)
        return SourceMetadata(
            locator=entry["path_lower"],
            filename=entry["name"],
            extension=Path(entry["name"]).suffix.lower(),
            mime_type=mimetypes.guess_type(entry["name"])[0] or "application/octet-stream",
            size=entry["size"],
            modified_at=_parse_dropbox_timestamp(entry["server_modified"]),
            remote_revision=entry["rev"],
            content_hash=self.content_hash(locator),
        )

    def download(self, locator: str) -> bytes:
        try:
            response = self._session.post(
                f"{CONTENT_BASE_URL}/files/download",
                headers=self._headers(**{"Dropbox-API-Arg": json.dumps({"path": locator})}),
                timeout=self._timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise DropboxConnectorError(f"Dropbox download request failed for {locator!r}: {exc}") from exc
        if response.status_code != 200:
            raise DropboxConnectorError(
                f"Dropbox download failed for {locator!r}: HTTP "
                f"{response.status_code}: {response.text[:500]}"
            )
        return response.content

    def revision(self, locator: str) -> str:
        """Dropbox's own `rev` field — cheap (metadata-only), independent
        of content_hash, exactly the connector-native version marker the
        contract asks for."""
        return self._get_file_entry(locator)["rev"]

    def content_hash(self, locator: str) -> str:
        """A real SHA-256 of the downloaded bytes, not Dropbox's own
        differently-computed content_hash field (see module docstring)."""
        payload = self.download(locator)
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"

    def _get_file_entry(self, locator: str) -> dict[str, Any]:
        entry = self._rpc("files/get_metadata", {"path": locator})
        if entry.get(".tag") != "file":
            raise DropboxConnectorError(
                f"locator is not a file: {locator!r} (tag={entry.get('.tag')!r})"
            )
        return entry


def _parse_dropbox_timestamp(value: str) -> datetime:
    """Dropbox timestamps are always UTC, formatted like
    '2026-01-15T10:30:00Z' (ISO 8601, second precision, literal 'Z') —
    per Dropbox API v2's documented Timestamp format."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
