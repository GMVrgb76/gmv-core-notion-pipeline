import sys

import pytest
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
import gmv_work_notes_normalize as wn


def _root(tmp_path: Path) -> Path:
    for sub in ("inbox/note", "inbox/mail", "gbrain"):
        (tmp_path / sub).mkdir(parents=True)
    return tmp_path


def _eml(path: Path, *, subject="Preventivo cantiere", body="Ciao,\nvedi sotto.", html=None,
         headers=None, attachment=None, msg_id="<abc@proton.me>") -> None:
    m = EmailMessage()
    m["From"] = "Mario Rossi <mario@example.com>"
    m["To"] = "me@proton.me"
    m["Subject"] = subject
    m["Date"] = "Tue, 14 Oct 2026 09:30:00 +0200"
    if msg_id:
        m["Message-ID"] = msg_id
    for k, v in (headers or {}).items():
        m[k] = v
    if html:
        m.set_content(html, subtype="html")
    else:
        m.set_content(body)
    if attachment:
        m.add_attachment(b"x", maintype="application", subtype="pdf", filename=attachment)
    path.write_bytes(bytes(m))


def _out(root: Path, prefix: str) -> list[Path]:
    return sorted((root / "gbrain" / prefix).glob("*.md"))


def test_note_without_frontmatter_gets_title_type_tags(tmp_path):
    root = _root(tmp_path)
    (root / "inbox/note/idee.txt").write_text("# Riunione cantiere\n\nPunti: A, B", encoding="utf-8")
    assert wn.run(root)["written"] == 1
    out = _out(root, "note-lavoro")[0].read_text(encoding="utf-8")
    assert 'title: "Riunione cantiere"' in out
    assert 'type: "note"' in out
    assert 'tags: ["nota-lavoro"]' in out
    assert "Punti: A, B" in out


def test_note_title_falls_back_to_filename_not_placeholder(tmp_path):
    root = _root(tmp_path)
    (root / "inbox/note/appunti_vari.md").write_text("solo testo", encoding="utf-8")
    wn.run(root)
    assert 'title: "appunti vari"' in _out(root, "note-lavoro")[0].read_text(encoding="utf-8")


def test_note_existing_frontmatter_preserved_and_title_kept(tmp_path):
    root = _root(tmp_path)
    (root / "inbox/note/n.md").write_text("---\ntitle: Mio titolo\nautore: gmv\n---\n\ncorpo", encoding="utf-8")
    wn.run(root)
    out = _out(root, "note-lavoro")[0].read_text(encoding="utf-8")
    assert 'title: "Mio titolo"' in out
    assert "autore: gmv" in out
    assert out.count("title:") == 1


def test_originals_untouched_and_rerun_idempotent(tmp_path):
    root = _root(tmp_path)
    src = root / "inbox/note/a.md"
    src.write_text("# A\n\nx", encoding="utf-8")
    before = src.read_bytes()
    assert wn.run(root)["written"] == 1
    second = wn.run(root)
    assert second == {"written": 0, "unchanged": 1, "skipped_bulk": 0, "not_mail": 0, "errors": 0, "attachment_pages": 0, "attachments_no_text": 0}
    assert src.read_bytes() == before


def test_note_edit_updates_same_output_file(tmp_path):
    root = _root(tmp_path)
    src = root / "inbox/note/a.md"
    src.write_text("# A\n\nuno", encoding="utf-8")
    wn.run(root)
    src.write_text("# A\n\ndue", encoding="utf-8")
    wn.run(root)
    outs = _out(root, "note-lavoro")
    assert len(outs) == 1 and "due" in outs[0].read_text(encoding="utf-8")


def test_mail_frontmatter_and_body(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml")
    wn.run(root)
    out = _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")
    assert 'title: "Preventivo cantiere"' in out
    assert 'type: "email"' in out
    assert 'tags: ["mail-lavoro"]' in out
    assert 'date: "2026-10-14"' in out
    assert 'message_id: "<abc@proton.me>"' in out
    assert "vedi sotto." in out


def test_mail_subject_with_colon_and_quotes_is_valid_quoted_yaml(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", subject='Re: "urgente": offerta')
    wn.run(root)
    assert 'title: "Re: \\"urgente\\": offerta"' in _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")


def test_mail_quoted_text_and_reply_header_stripped(tmp_path):
    root = _root(tmp_path)
    body = "Confermo.\n\nOn Mon, 13 Oct 2026, Mario wrote:\n> vecchio testo\n> altro"
    _eml(root / "inbox/mail/1.eml", body=body)
    wn.run(root)
    out = _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")
    assert "Confermo." in out
    assert "vecchio testo" not in out


def test_mail_html_only_converted_to_text(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", html="<html><style>p{}</style><p>Ciao <b>mondo</b></p></html>")
    wn.run(root)
    out = _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")
    assert "Ciao mondo" in out and "<b>" not in out and "p{}" not in out


def test_mail_attachment_names_listed_not_imported(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", attachment="contratto.pdf")
    wn.run(root)
    out = _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")
    assert "- contratto.pdf" in out


def test_bulk_mail_imported_by_default_and_skipped_on_flag(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/news.eml", headers={"List-Unsubscribe": "<mailto:u@x.com>"})
    assert wn.run(root, skip_bulk=True)["skipped_bulk"] == 1
    assert _out(root, "mail-lavoro") == []
    assert wn.run(root)["written"] == 1


def test_same_message_id_in_two_files_yields_one_output(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/a.eml")
    _eml(root / "inbox/mail/b.eml")
    wn.run(root)
    assert len(_out(root, "mail-lavoro")) == 1


def test_mail_without_message_id_still_gets_stable_name(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/a.eml", msg_id=None)
    wn.run(root)
    first = [p.name for p in _out(root, "mail-lavoro")]
    wn.run(root)
    assert [p.name for p in _out(root, "mail-lavoro")] == first and len(first) == 1


def test_corrupt_eml_counts_as_error_and_others_still_processed(tmp_path):
    root = _root(tmp_path)
    (root / "inbox/mail/bad.eml").write_bytes(b"\xff\xfe\x00 garbage")
    _eml(root / "inbox/mail/ok.eml")
    stats = wn.run(root)
    assert stats["written"] >= 1
    assert any("Preventivo" in p.read_text(encoding="utf-8") for p in _out(root, "mail-lavoro"))


def test_note_empty_heading_line_does_not_leak_next_line_into_title(tmp_path):
    root = _root(tmp_path)
    (root / "inbox/note/m.md").write_text("#   \n# Meeting Summary\n\ntesto", encoding="utf-8")
    wn.run(root)
    assert 'title: "Meeting Summary"' in _out(root, "note-lavoro")[0].read_text(encoding="utf-8")


def test_mail_confidentiality_footer_removed(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", body="Testo utile.\n\nCONFIDENTIALITY NOTICE - This message is private")
    wn.run(root)
    out = _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")
    assert "Testo utile." in out and "CONFIDENTIALITY" not in out


NESTED_EML = b"""From: a@example.com
To: b@example.com
Subject: Annidata
Date: Tue, 14 Oct 2026 09:30:00 +0200
Message-ID: <nested@x>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="OUT"

--OUT
Content-Type: multipart/mixed; boundary="IN"

--IN
Content-Type: multipart/related; boundary="REL"

--REL
Content-Type: text/html; charset=utf-8

<p>Corpo html</p>
--REL
Content-Type: image/png; name="logo.png"
Content-Disposition: inline; filename="logo.png"
Content-Transfer-Encoding: base64

iVBORw0KGgo=
--REL--
--IN
Content-Type: application/pdf; name="bonifico.pdf"
Content-Disposition: attachment; filename="bonifico.pdf"
Content-Transfer-Encoding: base64

JVBERi0=
--IN--
--OUT--
"""


def test_nested_multipart_lists_real_attachment_but_not_inline_images(tmp_path):
    root = _root(tmp_path)
    (root / "inbox/mail/n.eml").write_bytes(NESTED_EML)
    wn.run(root)
    out = _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")
    assert "Corpo html" in out
    assert "- bonifico.pdf" in out and "logo.png" not in out


def test_html_table_whitespace_lines_collapsed(tmp_path):
    root = _root(tmp_path)
    html = "<table><tr><td>   </td></tr>" + "<tr><td>   </td></tr>" * 6 + "<tr><td>Premio addebitato</td></tr></table>"
    _eml(root / "inbox/mail/1.eml", html=html)
    wn.run(root)
    out = _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")
    assert "Premio addebitato" in out
    assert "\n\n\n" not in out
    assert all(line == line.rstrip() for line in out.splitlines())


def test_mail_without_eml_extension_and_with_mbox_from_line_is_imported(tmp_path):
    root = _root(tmp_path)
    raw = b"From sender@example.com Thu Oct 08 16:42:59 2026\nFrom: s@example.com\nSubject: Infiltrazione\nDate: Thu, 8 Oct 2026 16:42:59 +0000\nMessage-ID: <i@x>\n\nTesto"
    (root / "inbox/mail/R_ Infiltrazione Visconti 8_1 - Milano").write_bytes(raw)
    assert wn.run(root)["written"] == 1
    assert 'title: "Infiltrazione"' in _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")


def test_non_mail_file_in_inbox_mail_is_skipped_not_error(tmp_path):
    root = _root(tmp_path)
    (root / "inbox/mail/random.bin").write_bytes(b"\x00\x01 not an email")
    (root / "inbox/mail/appunti.json").write_text("{}", encoding="utf-8")
    stats = wn.run(root)
    assert stats["not_mail"] == 1 and stats["errors"] == 0 and _out(root, "mail-lavoro") == []


def test_forwarded_message_content_is_kept(tmp_path):
    root = _root(tmp_path)
    body = "Ti inoltro.\n\n---------- Forwarded message ---------\nDa: X\n\nContenuto importante inoltrato"
    _eml(root / "inbox/mail/1.eml", body=body)
    wn.run(root)
    assert "Contenuto importante inoltrato" in _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")


def test_html_mislabelled_as_plain_text_is_converted(tmp_path):
    root = _root(tmp_path)
    html = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0//EN"><html><head><style>p{}</style></head><body><p>Documentazione <b>firmata</b></p></body></html>'
    _eml(root / "inbox/mail/1.eml", body=html)
    wn.run(root)
    out = _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")
    assert "Documentazione firmata" in out
    assert "<html" not in out.lower() and "DOCTYPE" not in out and "p{}" not in out


def test_plain_text_mentioning_html_tag_midway_is_untouched(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", body="Usa il tag <html> nel template.")
    wn.run(root)
    assert "<html>" in _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")


LONG_TEXT = "Clausola contrattuale numero uno. " * 20


def _fake_pdf(texts):
    return lambda data: (texts[data], "pdftotext") if data in texts else None


def test_pdf_attachment_becomes_separate_linked_page(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", attachment="contratto.pdf")
    stats = wn.run(root, pdf_text=_fake_pdf({b"x": LONG_TEXT}))
    assert stats["attachment_pages"] == 1 and stats["attachments_no_text"] == 0
    att = _out(root, "mail-lavoro-allegati")[0]
    body = att.read_text(encoding="utf-8")
    assert 'type: "source"' in body and 'tags: ["allegato-mail"]' in body
    assert "Clausola contrattuale" in body and "contratto.pdf (allegato a: Preventivo cantiere)" in body
    mail = _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")
    assert f"[[mail-lavoro-allegati/{att.stem}]]" in mail
    assert "Clausola contrattuale" not in mail


def test_scanned_pdf_is_flagged_and_not_imported(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", attachment="scan.pdf")
    stats = wn.run(root, pdf_text=_fake_pdf({b"x": "   "}))
    assert stats["attachment_pages"] == 0 and stats["attachments_no_text"] == 1
    assert _out(root, "mail-lavoro-allegati") == []
    assert "scan.pdf (scansione" in _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")


def test_extractor_failure_counts_as_no_text_not_error(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", attachment="a.pdf")
    stats = wn.run(root, pdf_text=_fake_pdf({}))
    assert stats["attachments_no_text"] == 1 and stats["errors"] == 0


def test_same_attachment_in_two_mails_yields_one_page(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", attachment="a.pdf", msg_id="<1@x>", subject="Uno")
    _eml(root / "inbox/mail/2.eml", attachment="a.pdf", msg_id="<2@x>", subject="Due")
    stats = wn.run(root, pdf_text=_fake_pdf({b"x": LONG_TEXT}))
    assert stats["attachment_pages"] == 1 and len(_out(root, "mail-lavoro-allegati")) == 1
    assert len(_out(root, "mail-lavoro")) == 2


def test_long_attachment_is_split_into_parts():
    text = "\n\n".join(f"Paragrafo {i} " + "x" * 900 for i in range(120))
    parts = wn.split_text(text, limit=20_000)
    assert len(parts) > 1 and all(len(p) <= 20_000 for p in parts)
    assert "\n\n".join(parts) == text


def test_oversized_single_paragraph_is_hard_split():
    parts = wn.split_text("y" * 25_000, limit=10_000)
    assert [len(p) for p in parts] == [10_000, 10_000, 5_000]


def test_pdf_text_cache_avoids_second_extraction(tmp_path):
    calls = []

    def extractor(data):
        calls.append(1)
        return "testo"

    get = wn.make_cached_pdf_text(tmp_path / "cache", extractor)
    assert get(b"abc") == ("testo", "pdftotext") and get(b"abc") == ("testo", "pdftotext")
    assert len(calls) == 1


def test_failed_extraction_is_not_cached(tmp_path):
    results = iter([None, "ok"])
    get = wn.make_cached_pdf_text(tmp_path / "cache", lambda d: next(results))
    assert get(b"abc") is None
    assert get(b"abc") == ("ok", "pdftotext")


def test_clean_layout_collapses_blank_lines_and_page_breaks():
    out = wn.clean_layout("a      b   \n\n\n\n\fpagina due\n")
    assert out == "a   b\n\npagina due"


def test_without_extractor_attachments_are_only_listed(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", attachment="c.pdf")
    stats = wn.run(root)
    assert stats["attachment_pages"] == 0 and stats["attachments_no_text"] == 0
    assert "- c.pdf (non importato)" in _out(root, "mail-lavoro")[0].read_text(encoding="utf-8")


def _ocr_get(tmp_path, ocr, base=""):
    return wn.make_cached_pdf_text(tmp_path / "cache", lambda d: base, ocr=ocr)


def test_image_only_pdf_falls_through_to_ocr_and_is_cached(tmp_path):
    calls = []

    def ocr(data):
        calls.append(1)
        return "Testo riconosciuto dall'OCR"

    get = _ocr_get(tmp_path, ocr)
    assert get(b"scan") == ("Testo riconosciuto dall'OCR", "ocr")
    assert get(b"scan") == ("Testo riconosciuto dall'OCR", "ocr")
    assert len(calls) == 1


def test_ocr_not_invoked_when_text_layer_is_enough(tmp_path):
    get = _ocr_get(tmp_path, lambda d: pytest.fail("OCR must not run"), base="x" * wn.MIN_TEXT_CHARS)
    assert get(b"doc")[1] == "pdftotext"


def test_ocr_failure_is_not_cached_and_keeps_text_layer_result(tmp_path):
    results = iter([None, "Riconosciuto al secondo tentativo"])
    get = _ocr_get(tmp_path, lambda d: next(results))
    assert get(b"scan") == ("", "pdftotext")
    assert get(b"scan") == ("Riconosciuto al secondo tentativo", "ocr")


def test_budgeted_ocr_stops_when_pages_are_spent():
    spent = []
    run_ocr = wn.make_budgeted_ocr(3, ocr=lambda d, pages: spent.append(pages) or "t", page_count=lambda d: 2)
    assert run_ocr(b"a") == "t"
    assert run_ocr(b"b") is None
    assert spent == [2]


def test_ocr_page_becomes_attachment_page_marked_as_ocr(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", attachment="scan.pdf")
    get = _ocr_get(tmp_path, lambda d: "Avviso condominiale. " * 20)
    stats = wn.run(root, pdf_text=get)
    assert stats["attachment_pages"] == 1 and stats["attachments_no_text"] == 0
    body = _out(root, "mail-lavoro-allegati")[0].read_text(encoding="utf-8")
    assert 'extraction: "ocr"' in body and 'source_kind: "eml_attachment_pdf_ocr"' in body


def test_budget_exhausted_leaves_scan_flagged_for_next_run(tmp_path):
    root = _root(tmp_path)
    _eml(root / "inbox/mail/1.eml", attachment="scan.pdf")
    exhausted = wn.make_budgeted_ocr(0, ocr=lambda d, p: "mai", page_count=lambda d: 1)
    stats = wn.run(root, pdf_text=_ocr_get(tmp_path, exhausted))
    assert stats["attachment_pages"] == 0 and stats["attachments_no_text"] == 1
