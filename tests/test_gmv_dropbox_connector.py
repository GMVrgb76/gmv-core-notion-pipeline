"""Crawler preplan step 9: Dropbox SourceConnector.

No real network calls: `requests.Session` is injected with a fake that
records every call and returns canned responses, since this repo has no
HTTP-mocking dependency and adding one would be a new dependency for a
single module. Cross-checks against the real, already-committed
`gmv_crawler_contracts` module (CONTENT_HASH_PATTERN, SourceListing,
SourceMetadata, SourceConnector Protocol) rather than re-asserting a
duplicated shape -- same discipline steps 4/6/7/8/10 already used.
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import requests

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_crawler_contracts import (  # noqa: E402
    CONTENT_HASH_PATTERN,
    SourceConnector,
    SourceListing,
    SourceMetadata,
)
from gmv_dropbox_connector import (  # noqa: E402
    DropboxConnector,
    DropboxConnectorError,
    _parse_dropbox_timestamp,
)


@dataclass
class FakeResponse:
    status_code: int
    body: Any = None
    content: bytes = b""

    def json(self) -> Any:
        return self.body

    @property
    def text(self) -> str:
        return str(self.body)


@dataclass
class FakeSession:
    """Queues one FakeResponse per URL (FIFO); records every call made."""

    queued: dict[str, list[FakeResponse]] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def queue(self, url: str, response: FakeResponse) -> None:
        self.queued.setdefault(url, []).append(response)

    def post(self, url: str, *, headers=None, json=None, timeout=None) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        pending = self.queued.get(url)
        if not pending:
            raise AssertionError(f"no queued response for {url}")
        return pending.pop(0)


FILE_ENTRY = {
    ".tag": "file",
    "name": "Report.pdf",
    "path_lower": "/artists/report.pdf",
    "server_modified": "2026-01-15T10:30:00Z",
    "size": 1234,
    "rev": "abc123def",
    "content_hash": "0" * 64,  # Dropbox's own (different) algorithm -- must NOT be reused
}
FOLDER_ENTRY = {".tag": "folder", "name": "Subfolder", "path_lower": "/artists/subfolder"}
DELETED_ENTRY = {".tag": "deleted", "name": "Old.pdf", "path_lower": "/artists/old.pdf"}


def make_connector(session: FakeSession, **kwargs) -> DropboxConnector:
    return DropboxConnector(access_token="test-token", session=session, **kwargs)  # noqa: S106 (test fixture, not a real secret)


def test_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DROPBOX_ACCESS_TOKEN", raising=False)
    with pytest.raises(DropboxConnectorError, match="no Dropbox access token"):
        DropboxConnector(session=FakeSession())


def test_token_from_env_var_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DROPBOX_ACCESS_TOKEN", "env-token")
    connector = DropboxConnector(session=FakeSession())
    assert connector._token == "env-token"  # noqa: S105,SLF001 (test fixture, not a real secret; verifying the fallback actually ran)


def test_explicit_token_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DROPBOX_ACCESS_TOKEN", "env-token")
    connector = DropboxConnector(access_token="explicit-token", session=FakeSession())  # noqa: S106 (test fixture, not a real secret)
    assert connector._token == "explicit-token"  # noqa: S105,SLF001 (test fixture, not a real secret)


def test_connector_satisfies_source_connector_protocol() -> None:
    connector = make_connector(FakeSession())
    assert isinstance(connector, SourceConnector)


def test_list_single_page_filters_non_file_entries() -> None:
    session = FakeSession()
    session.queue(
        "https://api.dropboxapi.com/2/files/list_folder",
        FakeResponse(200, {"entries": [FILE_ENTRY, FOLDER_ENTRY, DELETED_ENTRY], "has_more": False}),
    )
    connector = make_connector(session, root_path="/artists")
    listings = connector.list()
    assert listings == [
        SourceListing(
            locator="/artists/report.pdf",
            filename="Report.pdf",
            size=1234,
            modified_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )
    ]


def test_list_sends_root_path_recursive_and_excludes_deleted() -> None:
    session = FakeSession()
    session.queue(
        "https://api.dropboxapi.com/2/files/list_folder",
        FakeResponse(200, {"entries": [], "has_more": False}),
    )
    make_connector(session, root_path="/artists").list()
    call = session.calls[0]
    assert call["json"] == {"path": "/artists", "recursive": True, "include_deleted": False}


def test_list_sends_bearer_token_in_authorization_header() -> None:
    session = FakeSession()
    session.queue(
        "https://api.dropboxapi.com/2/files/list_folder",
        FakeResponse(200, {"entries": [], "has_more": False}),
    )
    make_connector(session).list()
    assert session.calls[0]["headers"]["Authorization"] == "Bearer test-token"


def test_download_sends_bearer_token_in_authorization_header() -> None:
    session = FakeSession()
    session.queue(
        "https://content.dropboxapi.com/2/files/download",
        FakeResponse(200, content=b"bytes"),
    )
    make_connector(session).download("/artists/report.pdf")
    assert session.calls[0]["headers"]["Authorization"] == "Bearer test-token"


def test_list_follows_pagination_cursor() -> None:
    session = FakeSession()
    page_1 = dict(FILE_ENTRY, name="First.pdf", path_lower="/artists/first.pdf")
    page_2 = dict(FILE_ENTRY, name="Second.pdf", path_lower="/artists/second.pdf")
    session.queue(
        "https://api.dropboxapi.com/2/files/list_folder",
        FakeResponse(200, {"entries": [page_1], "has_more": True, "cursor": "cursor-1"}),
    )
    session.queue(
        "https://api.dropboxapi.com/2/files/list_folder/continue",
        FakeResponse(200, {"entries": [page_2], "has_more": False}),
    )
    listings = make_connector(session).list()
    assert [entry.filename for entry in listings] == ["First.pdf", "Second.pdf"]
    continue_call = session.calls[1]
    assert continue_call["json"] == {"cursor": "cursor-1"}


def test_list_raises_on_non_200() -> None:
    session = FakeSession()
    session.queue(
        "https://api.dropboxapi.com/2/files/list_folder",
        FakeResponse(401, {"error_summary": "invalid_access_token/..."}),
    )
    with pytest.raises(DropboxConnectorError, match="HTTP 401"):
        make_connector(session).list()


def test_rpc_network_failure_is_wrapped_not_propagated_raw() -> None:
    class RaisingSession:
        def post(self, *args, **kwargs):
            raise requests.exceptions.ConnectionError("connection reset by peer")

    with pytest.raises(DropboxConnectorError, match="connection reset by peer"):
        make_connector(RaisingSession()).list()


def test_download_network_failure_is_wrapped_not_propagated_raw() -> None:
    class RaisingSession:
        def post(self, *args, **kwargs):
            raise requests.exceptions.Timeout("timed out")

    with pytest.raises(DropboxConnectorError, match="timed out"):
        make_connector(RaisingSession()).download("/artists/report.pdf")


def test_download_sends_dropbox_api_arg_header_and_returns_raw_bytes() -> None:
    session = FakeSession()
    session.queue(
        "https://content.dropboxapi.com/2/files/download",
        FakeResponse(200, content=b"raw file bytes"),
    )
    payload = make_connector(session).download("/artists/report.pdf")
    assert payload == b"raw file bytes"
    call = session.calls[0]
    assert call["headers"]["Dropbox-API-Arg"] == '{"path": "/artists/report.pdf"}'


def test_download_raises_on_non_200_with_locator_in_message() -> None:
    session = FakeSession()
    session.queue(
        "https://content.dropboxapi.com/2/files/download",
        FakeResponse(409, {"error_summary": "path/not_found/..."}),
    )
    with pytest.raises(DropboxConnectorError, match=r"/artists/missing\.pdf"):
        make_connector(session).download("/artists/missing.pdf")


def test_revision_is_cheap_metadata_only_no_download_call() -> None:
    session = FakeSession()
    session.queue(
        "https://api.dropboxapi.com/2/files/get_metadata",
        FakeResponse(200, FILE_ENTRY),
    )
    revision = make_connector(session).revision("/artists/report.pdf")
    assert revision == "abc123def"
    assert [call["url"] for call in session.calls] == ["https://api.dropboxapi.com/2/files/get_metadata"]


def test_revision_raises_when_locator_is_not_a_file() -> None:
    session = FakeSession()
    session.queue("https://api.dropboxapi.com/2/files/get_metadata", FakeResponse(200, FOLDER_ENTRY))
    with pytest.raises(DropboxConnectorError, match="not a file"):
        make_connector(session).revision("/artists/subfolder")


def test_content_hash_is_real_sha256_not_dropboxs_own_content_hash_field() -> None:
    """The core correctness claim in the module docstring: Dropbox's own
    `content_hash` (FILE_ENTRY's all-zeros stand-in) must NOT be reused --
    the connector must independently compute a real SHA-256 of the
    downloaded bytes instead."""
    session = FakeSession()
    file_bytes = b"the real file content"
    session.queue(
        "https://content.dropboxapi.com/2/files/download",
        FakeResponse(200, content=file_bytes),
    )
    result = make_connector(session).content_hash("/artists/report.pdf")
    expected = f"sha256:{hashlib.sha256(file_bytes).hexdigest()}"
    assert result == expected
    assert result != f"sha256:{FILE_ENTRY['content_hash']}"
    assert CONTENT_HASH_PATTERN.match(result)


def test_metadata_returns_source_metadata_with_independently_computed_content_hash() -> None:
    session = FakeSession()
    file_bytes = b"pdf bytes for metadata test"
    session.queue("https://api.dropboxapi.com/2/files/get_metadata", FakeResponse(200, FILE_ENTRY))
    session.queue(
        "https://content.dropboxapi.com/2/files/download",
        FakeResponse(200, content=file_bytes),
    )
    result = make_connector(session).metadata("/artists/report.pdf")
    assert result == SourceMetadata(
        locator="/artists/report.pdf",
        filename="Report.pdf",
        extension=".pdf",
        mime_type="application/pdf",
        size=1234,
        modified_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        remote_revision="abc123def",
        content_hash=f"sha256:{hashlib.sha256(file_bytes).hexdigest()}",
    )


def test_metadata_raises_when_locator_is_not_a_file() -> None:
    session = FakeSession()
    session.queue("https://api.dropboxapi.com/2/files/get_metadata", FakeResponse(200, FOLDER_ENTRY))
    with pytest.raises(DropboxConnectorError, match="not a file"):
        make_connector(session).metadata("/artists/subfolder")


def test_metadata_unknown_extension_falls_back_to_octet_stream() -> None:
    session = FakeSession()
    entry = dict(FILE_ENTRY, name="Mystery.gmvxyz", path_lower="/artists/mystery.gmvxyz")
    session.queue("https://api.dropboxapi.com/2/files/get_metadata", FakeResponse(200, entry))
    session.queue("https://content.dropboxapi.com/2/files/download", FakeResponse(200, content=b"x"))
    result = make_connector(session).metadata("/artists/mystery.gmvxyz")
    assert result.mime_type == "application/octet-stream"


def test_parse_dropbox_timestamp_is_utc() -> None:
    parsed = _parse_dropbox_timestamp("2026-01-15T10:30:00Z")
    assert parsed == datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    assert parsed.tzinfo is timezone.utc
