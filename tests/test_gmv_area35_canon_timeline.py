"""GMV Area35 canon -> gbrain timeline extraction.

Pins the guarantees `10_API/gmv_area35_canon_timeline.py`'s own docstrings
claim, each attacked directly rather than re-read:

  Q1  a cross-year day range ("9 novembre 2015-17 gennaio 2016") parses whole,
      never fusing the range tail into a bogus same-month range
      -> test_cross_year_range_parses_whole
  Q2  a same-month two-day range ("13-19 febbraio 2015.") parses as a range
      -> test_same_month_range_parses
  Q3  a cross-month range ("27 febbraio-5 marzo 2015.") shares the trailing year
      -> test_cross_month_range_shares_the_trailing_year
  Q4  a single documented day ("13 dicembre 2013, ore 18:30") yields one day,
      and the ", ore ..." tail can never leak into the date
      -> test_single_day_ignores_the_time_tail
  Q5  month-only values stay month-level and are reported, never written
      -> test_month_only_is_reported_not_written
  Q6  opening/closing pairs in prose ("apertura il X ... e chiusura il Y ...")
      parse as one range, not two separate days
      -> test_open_close_pair_parses_as_one_range
  Q7  a day-capable canonical label beats the same page's `Anno`
      -> test_day_label_beats_the_year_field
  Q8  two genuinely different day ranges on one page are a conflict, not a guess
      -> test_two_day_labels_on_one_page_are_a_conflict
  Q9  a page whose only date signal is a rejected label skips with that label
      named in the reason
      -> test_only_rejected_label_skips_and_is_named
  Q10 opening/marketing labels (Opening, Vernissage, Inaugurazione, Apertura)
      are never the basis of an entry, and never shadow a real Date line
      -> test_opening_labels_are_never_chosen
  Q11 the multi-venue signal: a label that names Area35 wins over another
      venue's dates elsewhere in the body (real In Itinere shape)
      -> test_area35_label_wins_over_other_venue_dates
  Q12 year-only pages produce a year-level row marked SKIP, never a fabricated
      month/day (real 12 Shoes shape)
      -> test_year_only_row_is_reported_never_written
  Q13 prose fallback fires only with a canonical marker phrase and only when no
      day-capable label exists (real Autofiction/Visions shapes)
      -> test_prose_marker_lines_produce_a_day_entry
  Q14 prose that the page flags as conflict survives no fallback (real
      Whitelight shape) and the reason says the prose was excluded
      -> test_conflict_flagged_prose_is_excluded
  Q15 a page with no date at all skips with "no date line found" (real
      Oasi/GREY STREET shapes), and an untitled page is still handled
      -> test_no_date_page_skips_with_the_real_reason
  Q16 the label-line reader accepts digit-bearing labels (`Date Area35`) but
      never a line whose first character is a digit (a prose date line can't
      masquerade as a label)
      -> test_label_reader_accepts_digit_labels_and_rejects_date_led_lines
  Q17 the whole pipeline agrees on the real canon directory: 95 event pages,
      and APPLY + month + year + skip rows total exactly that
      -> test_whole_real_canon_counts_match_when_present
  Q18 the real write path is exactly one `gbrain timeline-add` call per
      day-level page, with source/detail/request-id, and zero calls for the
      skipped/reported pages
      -> test_apply_makes_exactly_one_call_per_day_page
  Q19 the module never imports sqlite3 and never imports the Monad/atom
      pipeline (the EIC-10 wall), checked with `ast` not substrings
      -> test_module_never_imports_sqlite_or_the_atom_pipeline
  Q20 a date-shaped but unparseable label value is reported, not crashed on
      -> test_unparseable_date_value_is_reported_not_crashing
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

import gmv_area35_canon_timeline as timeline  # noqa: E402


CANON = """---
schema: GMV_NOTION_CANON_SNAPSHOT_V1
status: canon_unaudited
title: {title}
type: {kind}
---

# NOTION TITLE
{title}

# NOTION PAGE
{body}
"""


def _write_page(tmp_path: Path, slug: str, body: str, *, title: str = "Untitled",
                kind: str = "event") -> Path:
    path = tmp_path / f"{slug}.md"
    path.write_text(CANON.format(title=title, kind=kind, body=body), encoding="utf-8")
    return path


def _extract(tmp_path: Path, slug: str, body: str, *, title: str = "Untitled") -> timeline.Row:
    path = _write_page(tmp_path, slug, body, title=title)
    return timeline.extract_page(slug, path.read_text(encoding="utf-8")).row


# --- Q1/Q2/Q3/Q4/Q5/Q6: the value grammar ---

def test_cross_year_range_parses_whole() -> None:
    parsed = timeline.parse_value("9 novembre 2015-17 gennaio 2016.")
    assert parsed is not None
    assert (parsed.precision, parsed.start, parsed.end) == (
        "day", "2015-11-09", "2016-01-17",
    )


def test_same_month_range_parses() -> None:
    parsed = timeline.parse_value("13-19 febbraio 2015.")
    assert (parsed.precision, parsed.start, parsed.end) == (
        "day", "2015-02-13", "2015-02-19",
    )
    parsed = timeline.parse_value("2-28 febbraio 2017.")
    assert parsed is not None
    assert (parsed.start, parsed.end) == ("2017-02-02", "2017-02-28")


def test_cross_month_range_shares_the_trailing_year() -> None:
    parsed = timeline.parse_value("27 febbraio-5 marzo 2015.")
    assert (parsed.precision, parsed.start, parsed.end) == (
        "day", "2015-02-27", "2015-03-05",
    )


def test_single_day_ignores_the_time_tail() -> None:
    parsed = timeline.parse_value("13 dicembre 2013, ore 18:30")
    assert (parsed.precision, parsed.start, parsed.end) == (
        "day", "2013-12-13", "2013-12-13",
    )


def test_month_only_is_reported_not_written(tmp_path: Path) -> None:
    row = _extract(tmp_path, "slug-a", "Periodo indicato: novembre 2016")
    assert row.precision == "month"
    assert row.start == "2016-11"
    assert row.apply is False
    assert "timeline-add needs YYYY-MM-DD" in row.reason


def test_open_close_pair_parses_as_one_range() -> None:
    parsed = timeline.parse_value(
        "L'archivio conferma apertura il 23 aprile 2024 e chiusura il 24 maggio 2024."
    )
    assert parsed is not None
    assert (parsed.precision, parsed.start, parsed.end) == (
        "day", "2024-04-23", "2024-05-24",
    )


# --- Q7/Q8/Q9/Q10/Q11: label selection ---

def test_day_label_beats_the_year_field(tmp_path: Path) -> None:
    body = "Anno: 2022\nDate: 23 aprile-20 giugno 2022"
    row = _extract(tmp_path, "slug-b", body)
    assert row.apply is True
    assert row.start == "2022-04-23"
    assert row.source == "Date"


def test_two_day_labels_on_one_page_are_a_conflict(tmp_path: Path) -> None:
    body = "Date: 3 marzo – 7 aprile 2016\nPeriodo: 14 marzo – 14 maggio 2017"
    row = _extract(tmp_path, "slug-c", body)
    assert row.apply is False
    assert row.precision == "none"
    assert row.reason.startswith("conflicting day-level labels")
    assert "2016-03-03" in row.reason and "2017-03-14" in row.reason


def test_only_rejected_label_skips_and_is_named(tmp_path: Path) -> None:
    body = (
        "Date candidate: 2 dicembre 2015 – 28 gennaio 2016\n"
        "Date documentate / in conflitto: 26 luglio – 4 settembre 2019"
    )
    row = _extract(tmp_path, "slug-d", body)
    assert row.apply is False
    assert "Date candidate" in row.reason
    assert "in conflitto" in row.reason


def test_opening_labels_are_never_chosen(tmp_path: Path) -> None:
    body = (
        "Date: 3 marzo – 7 aprile 2016\n"
        "Opening: 2 marzo 2016, ore 18:00\n"
        "Vernissage: 2 marzo 2016\n"
        "Inaugurazione: 2 marzo 2016\n"
        "Apertura: 2 marzo 2016"
    )
    row = _extract(tmp_path, "slug-e", body)
    assert row.apply is True
    assert row.start == "2016-03-03"
    assert "Opening" in row.notes and "Vernissage" in row.notes

    only_opening = _extract(tmp_path, "slug-f", "Vernissage: 2 marzo 2016\nOpening: 2 marzo 2016")
    assert only_opening.apply is False
    assert "Opening" in only_opening.reason


def test_area35_label_wins_over_other_venue_dates(tmp_path: Path) -> None:
    body = (
        "Date Area35: 13 aprile – 6 maggio 2012\n"
        "Date NAMI: 6 marzo 2025 – 10 aprile 2025"
    )
    row = _extract(tmp_path, "slug-g", body)
    assert row.apply is True
    assert (row.start, row.end) == ("2012-04-13", "2012-05-06")
    assert "Date NAMI" in row.notes


# --- Q12/Q13/Q14/Q15: precision and skip shapes ---

def test_year_only_row_is_reported_never_written(tmp_path: Path) -> None:
    row = _extract(tmp_path, "slug-h", "Anno: 2016")
    assert row.precision == "year"
    assert row.start == "2016"
    assert row.apply is False
    assert "only year precision" in row.reason


def test_prose_marker_lines_produce_a_day_entry(tmp_path: Path) -> None:
    body = (
        "AUTOFICTION\n"
        "Le date canoniche sono quelle pubblicate dal sito ufficiale della galleria: "
        "23 marzo–24 aprile 2026."
    )
    row = _extract(tmp_path, "slug-i", body)
    assert row.apply is True
    assert (row.start, row.end) == ("2026-03-23", "2026-04-24")
    assert row.source.startswith("prose")

    body2 = (
        "VISIONI\n"
        "Approvati come canonici: titolo, artista, sede e periodo 23 aprile–24 maggio 2024."
    )
    row2 = _extract(tmp_path, "slug-j", body2)
    assert row2.apply is True
    assert (row2.start, row2.end) == ("2024-04-23", "2024-05-24")


def test_conflict_flagged_prose_is_excluded(tmp_path: Path) -> None:
    body = (
        "Da verificare. L'indice ufficiale Area35 colloca la mostra 15 gennaio – 1 marzo 2019, "
        "mentre il testo interno riporta 15 gennaio – 15 febbraio 2018. Il conflitto va risolto."
    )
    row = _extract(tmp_path, "slug-k", body)
    assert row.apply is False
    assert "flagged non-canonical" in row.reason


def test_no_date_page_skips_with_the_real_reason(tmp_path: Path) -> None:
    row = _extract(tmp_path, "slug-l", "Nessuna data qui, solo testo.")
    assert row.apply is False
    assert row.reason == "no date line found"

    untitled = _extract(tmp_path, "slug-m", "Nessuna data qui.", title="")
    assert untitled.apply is False
    assert untitled.title == ""


def test_label_reader_accepts_digit_labels_and_rejects_date_led_lines() -> None:
    assert timeline.labelled_values("Date Area35: 13 aprile – 6 maggio 2012\n") == [
        ("Date Area35", "13 aprile – 6 maggio 2012"),
    ]
    assert timeline.labelled_values("2 aprile 2012: incontro con l'artista\n") == []


# --- Q17: agreement on the real canon directory (skipped when absent) ---

def test_whole_real_canon_counts_match_when_present() -> None:
    canon_dir = timeline.CANON_DIR
    if not canon_dir.is_dir():
        pytest.skip("03_STATE/area35_canon not present in this checkout")
    rows = [e.row for e in timeline.build_rows(canon_dir)]
    counts = {"day": 0, "month": 0, "year": 0, "none": 0}
    for r in rows:
        counts[r.precision] += 1
    assert len(rows) == 95
    assert counts["day"] == sum(1 for r in rows if r.apply)
    assert sum(counts.values()) == 95
    assert counts["none"] == 6


# --- Q18: the real write path, with a patched subprocess.run ---

def test_apply_makes_exactly_one_call_per_day_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canon = tmp_path / "canon"
    canon.mkdir()
    pages = [
        ("slug-1", "Date: 3 marzo – 7 aprile 2016", "In flore furoris", True),
        ("slug-2", "Periodo previsto: 9 novembre 2015-17 gennaio 2016", "Raggio", True),
        ("slug-3", "Anno: 2016", "Solo anno", False),
        ("slug-4", "Periodo indicato: novembre 2016", "Solo mese", False),
        ("slug-5", "Nessuna data.", "Niente", False),
    ]
    rows: list[timeline.Row] = []
    for slug, body, title, _applies in pages:
        path = _write_page(canon, slug, body, title=title)
        rows.append(timeline.extract_page(slug, path.read_text(encoding="utf-8")).row)

    calls: list[list[str]] = []

    class _Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(argv: list[str], **kwargs: object) -> _Result:
        calls.append(argv)
        return _Result()

    monkeypatch.setattr(timeline.subprocess, "run", fake_run)

    ok, failures = timeline.run_apply(rows, "gbrain")
    day_rows = [r for r in rows if r.apply]
    assert failures == []
    assert ok == len(day_rows) == 2
    for argv in calls:
        assert argv[0] == "gbrain"
        assert argv[1] == "timeline-add"
        assert len(argv[3]) == 10 and argv[3].count("-") == 2
        assert "--source" in argv and "gmv-area35-canon" in argv
        assert "--detail" in argv
        assert "--request-id" in argv
    assert [argv[2] for argv in calls] == ["slug-1", "slug-2"]


# --- Q19/Q20: walls and robustness ---

def test_module_never_imports_sqlite_or_the_atom_pipeline() -> None:
    source = (ROOT / "10_API" / "gmv_area35_canon_timeline.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "sqlite3" not in imported
    assert not any("monad" in name.lower() or "atom" in name.lower() for name in imported)


def test_unparseable_date_value_is_reported_not_crashing(tmp_path: Path) -> None:
    body = "Date: da verificare\nAnno: 2015–2016"
    extraction = timeline.extract_page(
        "slug-n",
        _write_page(tmp_path, "slug-n", body).read_text(encoding="utf-8"),
    )
    assert extraction.row.precision == "year"
    assert extraction.row.start == "2015"
    assert any("da verificare" in item for item in extraction.unparsed)