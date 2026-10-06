#!/usr/bin/env python3
"""Extract Area35 exhibition dates from the canon `event` pages into gbrain's timeline.

**What this is.** gbrain's own `gbrain extract timeline ... --infer-dates` heuristic
found all 95 real `event` pages under `03_STATE/area35_canon/` but produced zero
timeline entries — it cannot parse Italian month names or en-dash date ranges. The
canon files are therefore the only structured-enough source of exhibition dates that
exists, and the dates live only as free Italian prose on labelled lines. This module
reads the canon files (read-only), extracts the Area35-canonical date range per page
using the real label/format catalogue below, prints a dry-run report by default, and
only under an explicit `--apply` calls the real `gbrain timeline-add <slug> <date>
<text>` CLI once per page.

**Why read the canon files and not gbrain.** Read-only on this subsystem's own
already-written archive, no live-database dependency, and it sidesteps the PGLite
single-writer conflict — `gbrain extract`/`gbrain import`/`gbrain timeline` open the
engine file directly and collide with a running `gbrain serve --http`, while this
module needs no read from the engine at all (the write path is a CLI subprocess).

**Reported discipline.** One row per page: slug, title, precision (day/month/year),
start/end, the label or prose line the date came from, confidence, and action
(`APPLY` vs `SKIP: <real reason>`). Year-only pages are REPORTED, never written —
`timeline-add` demands `YYYY-MM-DD` and a fabricated month/day is precisely what the
brief forbids. `--apply` is never the default.

**The real label catalogue (read from all 95 event pages 2026-10-06, not guessed).**
Day-capable labels, canonical Area35: `Date`, `Date Area35`, `Date canoniche`,
`Date della mostra`, `Date in proprietà`, `Date pubbliche Area35`, `Data`,
`Data documentata`, `Data esposizione`, `Data registrata`, `Periodo`,
`Periodo documentato`, `Periodo dell'evento`, `Periodo comunicato`,
`Periodo contrattuale di uso stanza grande`, `Periodo indicato`, `Periodo previsto`,
`Periodo programmato`, `Apertura documentata`. Year-only labels: `Anno`,
`Anno indicato`, `Datazione archivistica`. Explicitly rejected (never the basis of
an entry, always listed when they are the only signal): `Date candidate`,
`Date documentate / in conflitto`, `Date nel PDF Dropbox`, `Date NAMI` (other venue),
`Date di apertura e chiusura` (`da verificare`), `Data esatta` (`da verificare`),
`Conflitto date`, `Durata`, and all opening/marketing labels — `Inaugurazione`,
`Opening`, `Opening su invito`, `Opening Area35`, `Vernissage`,
`Vernissage e conferenza stampa`, `Apertura` (the opening of a show is one event,
the show itself another; the pages distinguish them, so this module does too).

**Prose fallback.** A handful of real pages carry their date only as body prose with
no labelled line (verified: Autofiction, L'Europa durante la pioggia, L'Esplosione
dell'Uovo Cosmico, Visions Unveiled). The fallback only fires when no day-capable
label exists, only on body lines containing a month + a year AND one explicit
canonical marker phrase (`date canoniche`, `aperta dal`, `esposto dal`,
`esposta dal`, `apertura il`, `periodo `), and only when the line is not flagged
non-canonical (`conflitto`, `da verificare`, `provvisor*`, `mentre` conflict
narrative, `variante`, `preparatori`, ...). Exactly one distinct day range must
survive; anything else is reported and skipped.

**Confidence.** day-level from a canonical label = high; from a prose marker line =
high; from a planned/communicated label (`previsto`/`programmato`/`comunicato`/
`indicato`/`contrattuale`) = medium; month-level = medium; year-only = low.
`--apply` writes only day-level rows.

**The EIC-10 wall.** This module imports nothing from the Monad/atom/crawler
pipeline and has no atom-STATUS logic: the canon pages are `canon_unaudited`
derived Masters and stay that way. It writes no repo files at all, and makes no
`sqlite3` calls and no INSERT/UPDATE/DELETE: the only write is the
`gbrain timeline-add` subprocess, to the live engine.
"""

from __future__ import annotations

import argparse
import calendar
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANON_DIR = REPO_ROOT / "03_STATE" / "area35_canon"
SOURCE_SLUG = "default"

_MONTH = (
    r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|"
    r"ottobre|novembre|dicembre)"
)
_YEAR = r"(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)"
_DAY = r"(?<!\d)(\d{1,2})(?!\d)"
_SEP = r"\s*(?:–|—|-|al)\s*"

# Parsed in this order: a full cross-year range before a same-year cross-month range
# (otherwise "9 novembre 2015-17 gennaio 2016" mis-parses its tail), and the
# two-day-same-month shape strictly before the single-day shape.
RE_CROSS_YEAR = re.compile(rf"{_DAY} {_MONTH} {_YEAR}{_SEP}{_DAY} {_MONTH} {_YEAR}", re.I)
RE_CROSS_MONTH = re.compile(rf"{_DAY} {_MONTH}{_SEP}{_DAY} {_MONTH} {_YEAR}", re.I)
RE_SAME_MONTH = re.compile(rf"{_DAY}[-–—]\s*{_DAY} {_MONTH} {_YEAR}", re.I)
RE_OPEN_CLOSE = re.compile(
    rf"apertura il {_DAY} {_MONTH} {_YEAR}\s+e chiusura(?: il)?\s*{_DAY} {_MONTH} {_YEAR}",
    re.I,
)
RE_SINGLE = re.compile(rf"{_DAY} {_MONTH} {_YEAR}", re.I)
RE_MONTH_YEAR = re.compile(rf"{_MONTH} {_YEAR}", re.I)

_DAY_LABELS = {
    "Date", "Date Area35", "Date canoniche", "Date della mostra", "Date in proprietà",
    "Date pubbliche Area35", "Data", "Data documentata", "Data esposizione",
    "Data registrata", "Periodo", "Periodo comunicato",
    "Periodo contrattuale di uso stanza grande", "Periodo documentato",
    "Periodo dell'evento", "Periodo indicato", "Periodo previsto",
    "Periodo programmato", "Apertura documentata",
}
_YEAR_LABELS = {"Anno", "Anno indicato", "Datazione archivistica"}
_REJECT_LABELS = {
    "Date candidate", "Date documentate / in conflitto", "Date nel PDF Dropbox",
    "Date NAMI", "Date di apertura e chiusura", "Data esatta", "Conflitto date",
    "Durata",
}
_OPENING_LABELS = {
    "Apertura", "Opening", "Opening su invito", "Opening Area35", "Vernissage",
    "Vernissage e conferenza stampa", "Inaugurazione",
    "Conferenza stampa e inaugurazione",
}
_PLANNED_HINT = ("previsto", "programmato", "comunicato", "indicato", "contrattuale")
_DATE_PREFIXES = ("Date", "Periodo", "Data")
_PROSE_MARKERS = (
    "date canoniche", "aperta dal", "esposto dal", "esposta dal", "apertura il",
    "periodo ",
)
_PROSE_EXCLUDES = (
    "da verificare", "conflitto", "discrepanza", "provvisor", "mentre",
    "incongruenza", "da corroborare", "non canonich", "variante", "preparatori",
    "lasciata vuota", "registrata come", "non vengono attribuite",
)

_MONTH_NAMES = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
    "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
    "novembre": 11, "dicembre": 12,
}

_VALUE_LABEL_RE = re.compile(r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9'’ /-]*):\s*(\S.*)$")
_YEAR_RANGE_RE = re.compile(
    r"(?<!\d)(1[89]\d{2}|20\d{2})\s*[-–—]\s*(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)"
)
_MONTH_YEAR_IN_LINE_RE = re.compile(rf"{_MONTH}\s+{_YEAR}", re.I)


@dataclass(frozen=True)
class Parsed:
    precision: str  # day | month | year
    start: str | None  # YYYY-MM-DD / YYYY-MM / YYYY
    end: str | None  # YYYY-MM-DD (ranges only)
    year: str | None  # YYYY for year-level rows


@dataclass(frozen=True)
class Row:
    slug: str
    title: str
    precision: str  # day | month | year | none
    start: str | None
    end: str | None
    source: str  # the winning label, or "prose (marker)"
    raw: str  # verbatim value/line the date came from
    confidence: str
    notes: str = ""
    reason: str = ""
    apply: bool = False


@dataclass(frozen=True)
class _Extraction:
    row: Row
    rejected: tuple[str, ...] = ()
    unparsed: tuple[str, ...] = ()
    unclassified: tuple[str, ...] = ()


def _day_from(d1: str, month1: str, y1: str, d2: str, month2: str, y2: str) -> Parsed | None:
    day1, day2 = int(d1), int(d2)
    m1 = _MONTH_NAMES[month1.lower()]
    m2 = _MONTH_NAMES[month2.lower()]
    year1, year2 = int(y1), int(y2)

    def valid(day: int, month: int, year: int) -> bool:
        return 1 <= day <= calendar.monthrange(year, month)[1]

    if not (valid(day1, m1, year1) and valid(day2, m2, year2)):
        return None
    start = f"{year1:04d}-{m1:02d}-{day1:02d}"
    end = f"{year2:04d}-{m2:02d}-{day2:02d}"
    if year1 == year2 and start > end:
        return None
    return Parsed("day", start, end, None)


def parse_value(value: str) -> Parsed | None:
    """Parse one real date-line value: day ranges before day before month, else None."""
    m = RE_CROSS_YEAR.search(value)
    if m:
        return _day_from(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6))
    m = RE_CROSS_MONTH.search(value)
    if m:
        return _day_from(m.group(1), m.group(2), m.group(5), m.group(3), m.group(4), m.group(5))
    m = RE_SAME_MONTH.search(value)
    if m:
        return _day_from(m.group(1), m.group(3), m.group(4), m.group(2), m.group(3), m.group(4))
    m = RE_OPEN_CLOSE.search(value)
    if m:
        return _day_from(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6))
    m = RE_SINGLE.search(value)
    if m:
        return _day_from(m.group(1), m.group(2), m.group(3), m.group(1), m.group(2), m.group(3))
    m = RE_MONTH_YEAR.search(value)
    if m:
        month = _MONTH_NAMES[m.group(1).lower()]
        return Parsed("month", f"{int(m.group(2)):04d}-{month:02d}", None, None)
    return None


def parse_year_value(value: str) -> Parsed:
    """Year-level parse for `Anno`-style labels (never fabricates a month/day)."""
    span = _YEAR_RANGE_RE.search(value)
    if span:
        return Parsed("year", span.group(1), span.group(2), span.group(2))
    m = re.search(_YEAR, value)
    if m:
        return Parsed("year", m.group(1), None, m.group(1))
    return Parsed("year", None, None, None)


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    parts = text.split("---\n")
    if len(parts) < 3:
        return {}, text
    keys: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            keys[key] = value
    return keys, parts[2]


def labelled_values(body: str) -> list[tuple[str, str]]:
    return [
        (m.group(1), m.group(2))
        for line in body.splitlines()
        if (m := _VALUE_LABEL_RE.match(line))
    ]


def _confidence_for(label: str, parsed: Parsed) -> str:
    if parsed.precision == "day":
        if any(hint in label for hint in _PLANNED_HINT):
            return "medium (planned/contractual)"
        return "high"
    if parsed.precision == "month":
        return "medium"
    if parsed.precision == "year":
        return "low"
    return "-"


def _prose_day(body_lines: list[str]) -> tuple[Parsed, str, str] | str | None:
    """Prose-only fallback: -> (Parsed, line, marker) | "ambiguous" | None."""
    found: list[tuple[Parsed, str, str]] = []
    for line in body_lines:
        low = line.lower()
        if not _MONTH_YEAR_IN_LINE_RE.search(low):
            continue
        markers = [marker for marker in _PROSE_MARKERS if marker in low]
        if not markers:
            continue
        if any(flag in low for flag in _PROSE_EXCLUDES):
            continue
        parsed = parse_value(line)
        if parsed is not None and parsed.precision == "day":
            found.append((parsed, line.strip(), ";".join(markers)))
    if not found:
        return None
    distinct = {(p.start, p.end) for p, _, _ in found}
    if len(distinct) > 1:
        return "ambiguous"
    parsed, line, markers = found[0]
    return parsed, line, markers


def extract_page(slug: str, text: str) -> _Extraction:
    frontmatter, body = split_frontmatter(text)
    title = (frontmatter.get("title") or "").strip()
    if len(title) >= 2 and title[0] == title[-1] and title[0] in "'\"":
        title = title[1:-1]
    body_lines = body.splitlines()
    values = labelled_values(body)

    day_parsed: list[tuple[str, Parsed, str]] = []
    month_parsed: list[tuple[str, Parsed, str]] = []
    year_parsed: list[tuple[str, Parsed, str]] = []
    rejected: list[str] = []
    unparsed: list[str] = []
    unclassified: list[str] = []

    for label, value in values:
        if label in _DAY_LABELS:
            parsed = parse_value(value)
            if parsed is None:
                unparsed.append(f"{label}: {value}")
            elif parsed.precision == "day":
                day_parsed.append((label, parsed, value))
            elif parsed.precision == "month":
                month_parsed.append((label, parsed, value))
        elif label in _YEAR_LABELS:
            year_parsed.append((label, parse_year_value(value), value))
        elif label in _REJECT_LABELS or label in _OPENING_LABELS:
            rejected.append(f"{label}")
        elif label.startswith(_DATE_PREFIXES):
            unclassified.append(label)

    notes = ""
    if rejected:
        notes = "excluded labels: " + "; ".join(rejected)

    def row_for(parsed: Parsed, source: str, raw: str, confidence: str) -> Row:
        if parsed.precision == "day":
            return Row(
                slug=slug, title=title, precision="day", start=parsed.start,
                end=parsed.end, source=source, raw=raw, confidence=confidence,
                notes=notes, apply=True,
            )
        if parsed.precision == "month":
            return Row(
                slug=slug, title=title, precision="month", start=parsed.start,
                end=None, source=source, raw=raw, confidence=confidence, notes=notes,
                reason="only month precision; timeline-add needs YYYY-MM-DD",
            )
        shown = (
            f"{parsed.start}–{parsed.end}" if parsed.end else (parsed.start or "?")
        )
        return Row(
            slug=slug, title=title, precision="year", start=parsed.start,
            end=parsed.end, source=source, raw=raw, confidence=confidence,
            notes=notes, reason=f"only year precision ({shown}); timeline-add needs YYYY-MM-DD",
        )

    def skip_row(reason: str) -> _Extraction:
        return _Extraction(
            Row(slug, title, "none", None, None, "", "", "-", notes, reason),
            rejected=tuple(rejected), unparsed=tuple(unparsed),
            unclassified=tuple(unclassified),
        )

    if day_parsed:
        distinct = {(p.start, p.end) for _, p, _ in day_parsed}
        if len(distinct) > 1:
            shown = "; ".join(
                f"{p.start}–{p.end}" if p.end else p.start for _, p, _ in day_parsed
            )
            return skip_row("conflicting day-level labels: " + shown)
        label, parsed, raw = day_parsed[0]
        return _Extraction(
            row_for(parsed, label, raw, _confidence_for(label, parsed)),
            rejected=tuple(rejected), unparsed=tuple(unparsed),
            unclassified=tuple(unclassified),
        )

    prose = _prose_day(body_lines)
    if isinstance(prose, tuple):
        parsed, line, markers = prose
        return _Extraction(
            row_for(parsed, f"prose ({markers})", line, "high"),
            rejected=tuple(rejected), unparsed=tuple(unparsed),
            unclassified=tuple(unclassified),
        )

    if month_parsed:
        distinct = {(p.start, p.end) for _, p, _ in month_parsed}
        if len(distinct) > 1:
            shown = "; ".join(str(p.start) for _, p, _ in month_parsed)
            return skip_row("conflicting month-level labels: " + shown)
        label, parsed, raw = month_parsed[0]
        return _Extraction(
            row_for(parsed, label, raw, _confidence_for(label, parsed)),
            rejected=tuple(rejected), unparsed=tuple(unparsed),
            unclassified=tuple(unclassified),
        )

    if year_parsed:
        label, parsed, raw = year_parsed[0]
        return _Extraction(
            row_for(parsed, label, raw, _confidence_for(label, parsed)),
            rejected=tuple(rejected), unparsed=tuple(unparsed),
            unclassified=tuple(unclassified),
        )

    if rejected:
        return skip_row("only non-canonical/conflicting/opening labels: " + "; ".join(rejected))
    if prose == "ambiguous":
        return skip_row("multiple distinct prose date ranges, none canonical")
    if any(
        _MONTH_YEAR_IN_LINE_RE.search(line.lower())
        and any(flag in line.lower() for flag in _PROSE_EXCLUDES)
        for line in body_lines
    ):
        return skip_row("prose date(s) present but flagged non-canonical/provisional (excluded)")
    return skip_row("no date line found")


def iter_event_files(canon_dir: Path) -> list[Path]:
    return sorted(p for p in canon_dir.glob("*.md") if _is_event_file(p))


def _is_event_file(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    frontmatter, _ = split_frontmatter(text)
    return frontmatter.get("type") == "event"


def build_rows(canon_dir: Path) -> list[_Extraction]:
    return [
        extract_page(path.stem, path.read_text(encoding="utf-8"))
        for path in iter_event_files(canon_dir)
    ]


def render_report(extractions: list[_Extraction], source: str = SOURCE_SLUG) -> str:
    rows = [e.row for e in extractions]
    head = (
        f"{'SLUG':<13} {'TITLE':<40} {'PREC':<6} {'START':<12} {'END':<12} "
        f"{'SOURCE':<34} {'CONF':<22} {'NOTES':<34} VERDICT"
    )
    line_width = 13 + 40 + 6 + 12 + 12 + 34 + 22 + 34 + 1
    lines = [
        "Area35 canon event pages -> gbrain timeline (dry run)",
        f"pages: {len(rows)}   source: {source}   write path: gbrain timeline-add <slug> YYYY-MM-DD <text>",
        "",
        head,
        "-" * line_width,
    ]
    for r in rows:
        start = r.start.replace("T", " ") if r.start else "-"
        end = r.end or "-"
        verdict = "APPLY" if r.apply else "SKIP"
        if r.reason:
            verdict += f": {r.reason}"
        title = r.title[:39] if len(r.title) > 39 else r.title
        lines.append(
            f"{r.slug[:13]:<13} {title:<40} {r.precision:<6} {start:<12} {end:<12} "
            f"{(r.source or '-')[:33]:<34} {r.confidence:<22} "
            f"{(r.notes or '-')[:33]:<34} {verdict}"
        )

    applied = [r for r in rows if r.apply]
    skip_rows = [r for r in rows if not r.apply and r.precision == "none"]
    month_only = [r for r in rows if r.precision == "month"]
    year_only = [r for r in rows if r.precision == "year"]

    lines += ["", "== summary =="]
    lines.append(f"APPLY (day-level):    {len(applied)}")
    lines.append(f"month-level only:     {len(month_only)}")
    lines.append(f"year-level only:      {len(year_only)}")
    lines.append(f"skipped:              {len(skip_rows)}")
    reasons: dict[str, int] = {}
    for r in skip_rows:
        reasons[r.reason] = reasons.get(r.reason, 0) + 1
    for reason, count in sorted(reasons.items()):
        lines.append(f"   - {reason}: {count}")

    unclassified = sorted({u for e in extractions for u in e.unclassified})
    unparsed = [u for e in extractions for u in e.unparsed]
    if unclassified:
        lines += ["", "== unclassified date-ish labels (human review) =="]
        lines += [f"   {u}" for u in unclassified]
    if unparsed:
        lines += ["", "== unparsed day-label values (human review) =="]
        lines += [f"   {u[:110]}" for u in unparsed]
    return "\n".join(lines)


def run_apply(rows: list[Row], gbrain: str, source: str = SOURCE_SLUG) -> tuple[int, list[str]]:
    ok = 0
    failures: list[str] = []
    for row in rows:
        if not row.apply or not row.start:
            continue
        summary = f"{row.title} — {row.start}"
        if row.end and row.end != row.start:
            summary += f"–{row.end}"
        summary += f" [{row.source}]"
        argv = [
            gbrain, "timeline-add", row.slug, row.start, summary,
            "--source", source, "--detail", row.raw,
            "--request-id", str(uuid.uuid4()),
        ]
        result = subprocess.run(  # noqa: S603 - fixed argv from module constants + a slug read from a canon filename; no shell
            argv, capture_output=True, text=True
        )
        if result.returncode != 0:
            failures.append(
                f"{row.slug}: {(result.stderr or result.stdout).strip()}"
            )
        else:
            ok += 1
    return ok, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract Area35 exhibition dates from canon event pages into gbrain's timeline."
    )
    parser.add_argument("--canon-dir", default=str(CANON_DIR), help="canon folder (read-only input)")
    parser.add_argument("--gbrain", default="gbrain", help="gbrain CLI binary")
    parser.add_argument("--source", default=SOURCE_SLUG, help="gbrain provenance source id (must exist; the canon pages live in 'default')")
    parser.add_argument("--apply", action="store_true", help="write entries via gbrain timeline-add (default: dry-run)")
    args = parser.parse_args(argv)

    canon_dir = Path(args.canon_dir)
    if not canon_dir.is_dir():
        parser.error(f"canon dir not found: {canon_dir}")
    extractions = build_rows(canon_dir)
    print(render_report(extractions, args.source))
    print()

    if args.apply:
        ok, failures = run_apply([e.row for e in extractions], args.gbrain, args.source)
        print(f"apply: {ok} timeline entries written")
        if failures:
            for failure in failures:
                print(f"   FAIL {failure}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())