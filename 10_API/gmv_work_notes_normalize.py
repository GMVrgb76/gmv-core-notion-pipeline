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
import sys
import unicodedata
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path

NOTE_EXTS = {".md", ".txt"}
NON_MAIL_EXTS = {".json", ".md", ".txt", ".part", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".docx", ".xlsx", ".zip", ".mbox"}
REPLY_MARKERS = (
    re.compile(r"^-{2,}\s*(original message|messaggio originale)", re.I),
    re.compile(r"^(on|il giorno)\s.+\s(wrote|ha scritto):?\s*$", re.I),
    re.compile(r"^sent with proton mail", re.I),
    re.compile(r"^confidentiality notice", re.I),
)
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


class NotMail(Exception):
    pass


def normalize_mail(path: Path, skip_bulk: bool) -> tuple[str, str] | None:
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
        if part.get_content_type() == "text/html":
            text = html_to_text(text)
    body = strip_quoted(text)
    attachments = [
        part.get_filename() or "(senza nome)"
        for part in msg.walk()
        if not part.is_multipart() and part.get_content_disposition() == "attachment"
    ]
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
    if attachments:
        out += ["", "## Allegati (non importati)", *[f"- {a}" for a in attachments]]
    name = f"mail-lavoro/{date}-{slugify(subject)}-{short_hash(key)}.md"
    return name, "\n".join(out).rstrip() + "\n"


def run(root: Path, skip_bulk: bool = False) -> dict[str, int]:
    inbox_note, inbox_mail, out_dir = root / "inbox/note", root / "inbox/mail", root / "gbrain"
    stats = {"written": 0, "unchanged": 0, "skipped_bulk": 0, "not_mail": 0, "errors": 0}
    seen: dict[str, Path] = {}

    def emit(name: str, content: str, src: Path) -> None:
        if name in seen:
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
                result = normalize_mail(p, skip_bulk)
                if result is None:
                    stats["skipped_bulk"] += 1
                else:
                    emit(*result, p)
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
    args = ap.parse_args(argv)
    stats = run(args.root, args.skip_bulk)
    print(json.dumps(stats))
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
