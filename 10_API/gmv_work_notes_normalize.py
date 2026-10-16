#!/usr/bin/env python3
"""Normalize work notes (.md/.txt) and Proton Mail .eml exports into gbrain-ready markdown.

Reads <root>/inbox/{note,mail}, writes <root>/gbrain/{note-lavoro,mail-lavoro}.
Originals are never modified. Output names are deterministic, reruns are idempotent.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

NOTE_EXTS = {".md", ".txt"}
NON_MAIL_EXTS = {".json", ".md", ".txt", ".part", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".docx", ".xlsx", ".zip", ".mbox"}
REPLY_MARKERS = (
    re.compile(r"^-{2,}\s*(original message|messaggio originale)", re.I),
    re.compile(r"^(on|il giorno)\s.+\s(wrote|ha scritto):?\s*$", re.I),
    re.compile(r"^sent with proton mail", re.I),
    re.compile(r"^confidentiality notice", re.I),
)
HTML_SNIFF = re.compile(r"\s*<(!doctype html|html[\s>])", re.I)
PDFTOTEXT = "/opt/homebrew/bin/pdftotext"
MIN_TEXT_CHARS = 200
PART_CHARS = 50_000
ATTACH_DIR = "mail-lavoro-allegati"
DEFAULT_CACHE = Path.home() / ".gmv_runtime" / "work_notes_cache"
PdfText = Callable[[bytes], "str | None"]
GENERATED_KEYS = {"title", "type", "tags", "date", "source_kind", "source_hash"}


def slugify(text: str, limit: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:limit].strip("-") or "senza-titolo"


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]


def yq(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_frontmatter(fields: dict[str, object], extra_lines: list[str] = ()) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(yq(v) for v in value)}]")
        else:
            lines.append(f"{key}: {yq(str(value))}")
    lines.extend(extra_lines)
    lines.append("---")
    return "\n".join(lines)


def split_frontmatter(text: str) -> tuple[dict[str, str], list[str], str]:
    """Return (known generated keys, other raw frontmatter lines, body)."""
    if not text.startswith("---\n"):
        return {}, [], text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, [], text
    block = text[4:end].splitlines()
    body = text[end + 4:].lstrip("\n")
    known: dict[str, str] = {}
    other: list[str] = []
    for line in block:
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m and m.group(1) in GENERATED_KEYS:
            known[m.group(1)] = m.group(2).strip().strip("\"'")
        else:
            other.append(line)
    return known, other, body


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def normalize_note(path: Path, inbox_note: Path) -> tuple[str, str]:
    rel = path.relative_to(inbox_note).as_posix()
    raw = path.read_text(encoding="utf-8", errors="replace")
    known, other, body = split_frontmatter(raw)
    title = known.get("title")
    if not title:
        m = re.search(r"^#[ \t]+(\S.*?)[ \t]*$", body, re.M)
        title = m.group(1) if m else path.stem.replace("_", " ").replace("-", " ")
    date = known.get("date") or dt.datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
    fm = render_frontmatter(
        {
            "title": title,
            "type": known.get("type") or "note",
            "tags": ["nota-lavoro"],
            "date": date,
            "source_kind": "work_note",
            "source_hash": short_hash(rel),
        },
        other,
    )
    name = f"note-lavoro/{date}-{slugify(title)}-{short_hash(rel)}.md"
    return name, f"{fm}\n\n{body.rstrip()}\n"


class _HtmlText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("br", "p", "div", "tr", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _HtmlText()
    parser.feed(html)
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


def strip_quoted(body: str) -> str:
    kept: list[str] = []
    for line in body.splitlines():
        if any(p.match(line.strip()) for p in REPLY_MARKERS):
            break
        if line.lstrip().startswith(">"):
            continue
        kept.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def is_bulk(msg) -> bool:
    precedence = (msg.get("Precedence") or "").lower()
    return bool(msg.get("List-Unsubscribe")) or precedence in ("bulk", "list", "junk")


def clean_layout(text: str) -> str:
    text = text.replace("\f", "\n\n")
    text = "\n".join(re.sub(r" {4,}", "   ", line.rstrip()) for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_pdf_text(data: bytes) -> str | None:
    """Text layer via pdftotext; None when the tool fails (retry next run), "" for image-only PDFs."""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            result = subprocess.run(  # noqa: S603  # gmv-floor-ok: fixed pdftotext argv, no shell, input is a temp file path
                [PDFTOTEXT, "-layout", tmp.name, "-"], capture_output=True, timeout=120
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
    if result.returncode != 0:
        return None
    return clean_layout(result.stdout.decode("utf-8", "replace"))


def make_cached_pdf_text(cache_dir: Path | None, extractor: PdfText = extract_pdf_text) -> PdfText:
    def get(data: bytes) -> str | None:
        key = hashlib.sha1(data, usedforsecurity=False).hexdigest()
        cached = cache_dir / f"{key}.txt" if cache_dir else None
        if cached is not None and cached.exists():
            return cached.read_text(encoding="utf-8")
        text = extractor(data)
        if text is not None and cached is not None:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(text, encoding="utf-8")
        return text

    return get


def split_text(text: str, limit: int = PART_CHARS) -> list[str]:
    parts: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        while len(para) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(para[:limit])
            para = para[limit:]
        if current and len(current) + len(para) + 2 > limit:
            parts.append(current)
            current = ""
        current = f"{current}\n\n{para}" if current else para
    if current:
        parts.append(current)
    return parts


def attachment_pages(filename: str, data: bytes, text: str, mail_subject: str) -> list[tuple[str, str]]:
    key = short_hash(hashlib.sha1(data, usedforsecurity=False).hexdigest())
    parts = split_text(text)
    pages = []
    for i, body in enumerate(parts, 1):
        suffix = f"-p{i}" if len(parts) > 1 else ""
        title = f"{filename} (allegato a: {mail_subject})" + (f" - parte {i}/{len(parts)}" if len(parts) > 1 else "")
        fm = render_frontmatter({
            "title": title,
            "type": "source",
            "tags": ["allegato-mail"],
            "source_kind": "eml_attachment_pdf",
            "source_hash": key,
            "attachment_filename": filename,
        })
        name = f"{ATTACH_DIR}/{slugify(filename)}-{key}{suffix}.md"
        pages.append((name, f"{fm}\n\n# {title}\n\n{body}\n"))
    return pages


class NotMail(Exception):
    pass


def normalize_mail(path: Path, skip_bulk: bool, pdf_text: PdfText | None = None) -> tuple[list[tuple[str, str, bool]], int] | None:
    msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    if not (msg.get("From") or msg.get("Subject")):
        raise NotMail(path.name)
    if skip_bulk and is_bulk(msg):
        return None
    subject = str(msg.get("Subject") or "").strip() or "(senza oggetto)"
    message_id = str(msg.get("Message-ID") or "").strip()
    sender = str(msg.get("From") or "")
    recipients = ", ".join(str(msg.get(h)) for h in ("To", "Cc") if msg.get(h))
    try:
        date = msg["Date"].datetime.date().isoformat()
    except Exception:
        date = dt.datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()

    part = msg.get_body(preferencelist=("plain", "html"))
    text = ""
    if part is not None:
        text = part.get_content()
        if part.get_content_type() == "text/html" or HTML_SNIFF.match(text):
            text = html_to_text(text)
    body = strip_quoted(text)
    extra_pages: list[tuple[str, str, bool]] = []
    attachment_lines: list[str] = []
    no_text = 0
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() != "attachment":
            continue
        filename = part.get_filename() or "(senza nome)"
        text = None
        if pdf_text is not None and filename.lower().endswith(".pdf"):
            text = pdf_text(part.get_payload(decode=True) or b"")
            if text is None or len(text) < MIN_TEXT_CHARS:
                no_text += 1
                attachment_lines.append(f"- {filename} (scansione o testo non estraibile, contenuto non importato)")
                continue
            pages = attachment_pages(filename, part.get_payload(decode=True), text, subject)
            extra_pages += [(n, c, True) for n, c in pages]
            links = ", ".join(f"[[{n[:-3]}]]" for n, _ in pages)
            attachment_lines.append(f"- {filename}: {links}")
        else:
            attachment_lines.append(f"- {filename} (non importato)")
    key = message_id or short_hash(f"{subject}|{date}|{sender}|{text}")
    in_reply_to = str(msg.get("In-Reply-To") or "").strip()

    fields: dict[str, object] = {
        "title": subject,
        "type": "email",
        "tags": ["mail-lavoro"],
        "date": date,
        "source_kind": "eml",
        "source_hash": short_hash(key),
        "from": sender,
        "to": recipients,
    }
    if message_id:
        fields["message_id"] = message_id
    if in_reply_to:
        fields["in_reply_to"] = in_reply_to
    out = [render_frontmatter(fields), "", f"# {subject}", "", body or "(corpo vuoto)"]
    if attachment_lines:
        out += ["", "## Allegati", *attachment_lines]
    name = f"mail-lavoro/{date}-{slugify(subject)}-{short_hash(key)}.md"
    return [(name, "\n".join(out).rstrip() + "\n", False), *extra_pages], no_text


def run(root: Path, skip_bulk: bool = False, pdf_text: PdfText | None = None) -> dict[str, int]:
    inbox_note, inbox_mail, out_dir = root / "inbox/note", root / "inbox/mail", root / "gbrain"
    stats = {"written": 0, "unchanged": 0, "skipped_bulk": 0, "not_mail": 0, "errors": 0, "attachment_pages": 0, "attachments_no_text": 0}
    seen: dict[str, Path] = {}

    def emit(name: str, content: str, src: Path, attachment: bool = False) -> None:
        if attachment:
            if name in seen:
                return
            stats["attachment_pages"] += 1
        elif name in seen:
            print(f"WARN: {src} collapses onto {seen[name]} (same output {name})", file=sys.stderr)
        seen[name] = src
        stats["written" if write_if_changed(out_dir / name, content) else "unchanged"] += 1

    if inbox_note.is_dir():
        for p in sorted(inbox_note.rglob("*")):
            if p.is_file() and p.suffix.lower() in NOTE_EXTS and not p.name.startswith("."):
                try:
                    emit(*normalize_note(p, inbox_note), p)
                except Exception as exc:
                    stats["errors"] += 1
                    print(f"ERROR {p}: {exc}", file=sys.stderr)
    if inbox_mail.is_dir():
        for p in sorted(inbox_mail.rglob("*")):
            if not p.is_file() or p.name.startswith(".") or p.suffix.lower() in NON_MAIL_EXTS:
                continue
            try:
                result = normalize_mail(p, skip_bulk, pdf_text)
                if result is None:
                    stats["skipped_bulk"] += 1
                else:
                    pages, no_text = result
                    stats["attachments_no_text"] += no_text
                    for name, content, is_attachment in pages:
                        emit(name, content, p, is_attachment)
            except NotMail:
                stats["not_mail"] += 1
                print(f"WARN not a mail, skipped: {p}", file=sys.stderr)
            except Exception as exc:
                stats["errors"] += 1
                print(f"ERROR {p}: {exc}", file=sys.stderr)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True, help="NOTE_E_MAIL_LAVORO folder")
    ap.add_argument("--skip-bulk", action="store_true", help="skip mail with List-Unsubscribe/bulk headers (also drops transactional mail sent via marketing platforms)")
    ap.add_argument("--no-attachments", action="store_true", help="do not extract PDF attachment text")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="PDF text cache (outside Dropbox)")
    args = ap.parse_args(argv)
    pdf_text = None if args.no_attachments else make_cached_pdf_text(args.cache_dir)
    stats = run(args.root, args.skip_bulk, pdf_text)
    print(json.dumps(stats))
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
