#!/usr/bin/env python3
"""Pinned DOCUMENTAL V2 compatibility release of the legacy Market Engine."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path.home() / "Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM"
MARKET_DIR = BASE / "02_IMMOBILI/00_MARKET"
COMPARABLES_DIR = BASE / "02_IMMOBILI/02_COMPARABLES"
REPORT = MARKET_DIR / "MARKET_REPORT.md"
STATUS = MARKET_DIR / "MARKET_STATUS.md"
EXCLUDED = {
    "MARKET_REPORT.md",
    "MARKET_STATUS.md",
    "README.md",
    "INDEX.md",
    "COMPARABLE_TEMPLATE.md",
}


def read_markdown_files(folder: Path) -> list[tuple[Path, str]]:
    if not folder.exists():
        return []
    files = []
    for path in sorted(folder.rglob("*.md")):
        if path.name in EXCLUDED:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        files.append((path, text))
    return files


def extract_headings(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("#")
    ][:8]


def extract_key_lines(text: str) -> list[str]:
    keywords = [
        "prezzo",
        "valore",
        "€/mq",
        "euro",
        "milione",
        "milioni",
        "trend",
        "domanda",
        "offerta",
        "vendita",
        "canone",
        "yield",
        "rendimento",
        "comparabile",
        "ristrutturazione",
        "criticità",
        "opportunità",
        "prossima azione",
        "azione",
    ]
    result = []
    for line in text.splitlines():
        clean = line.strip()
        if clean and len(clean) <= 220 and any(
            keyword in clean.lower() for keyword in keywords
        ):
            result.append(clean)
    return result[:12]


def extract_numbers(text: str) -> list[str]:
    patterns = [
        r"\b\d{1,3}(?:[.,]\d{3})+(?:,\d+)?\s*€",
        r"\b\d+(?:[.,]\d+)?\s*(?:M|mln|milioni|milione)\b",
        r"\b\d{3,6}\s*€/mq\b",
        r"\b\d+(?:[.,]\d+)?\s*%\b",
        r"\b\d+(?:[.,]\d+)?\s*mq\b",
    ]
    found = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    return list(dict.fromkeys(found))[:20]


def append_file_summary(lines: list[str], path: Path, text: str) -> None:
    lines.extend([f"### {path.stem}", "", f"Fonte: `{path.relative_to(BASE)}`", ""])
    headings = extract_headings(text)
    numbers = extract_numbers(text)
    key_lines = extract_key_lines(text)
    if headings:
        lines.append("Struttura documento:")
        lines.extend(f"- {heading}" for heading in headings)
        lines.append("")
    if numbers:
        lines.append("Dati numerici rilevati:")
        lines.extend(f"- {number}" for number in numbers)
        lines.append("")
    if key_lines:
        lines.append("Punti rilevanti:")
        lines.extend(f"- {line}" for line in key_lines)
        lines.append("")
    if not headings and not numbers and not key_lines:
        lines.extend(["- Nessun punto operativo rilevato automaticamente.", ""])


def main() -> int:
    market_files = read_markdown_files(MARKET_DIR)
    comparable_files = read_markdown_files(COMPARABLES_DIR)
    now = datetime.now()
    lines = [
        "# GMV MARKET REPORT",
        "",
        "Data:",
        now.strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "## STATO",
        "",
        "Engine: OK",
        "Versione: DOCUMENTAL V2",
        "",
        "## SINTESI",
        "",
        f"- File mercato letti: {len(market_files)}",
        f"- File comparables letti: {len(comparable_files)}",
        "",
        "## MARKET INTELLIGENCE",
        "",
    ]
    for path, text in market_files:
        append_file_summary(lines, path, text)

    lines.extend(["## COMPARABLES", ""])
    if comparable_files:
        for path, text in comparable_files:
            append_file_summary(lines, path, text)
    else:
        lines.extend(["- Nessun file comparables trovato.", ""])

    lines.extend(
        [
            "## PROSSIMO STEP",
            "",
            "- Normalizzare i file mercato con campi: zona, prezzo, €/mq, fonte, data, affidabilità.",
            "- Normalizzare i comparables con campi: immobile, superficie, richiesta, vendita stimata, stato, fonte.",
            "- Aggiungere Trend Engine.",
            "- Aggiungere Comparables Engine.",
            "- Integrare questa sezione nel Morning Brief.",
            "",
        ]
    )
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    STATUS.write_text(
        "# MARKET STATUS\n\n"
        f"updated: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        "engine: DOCUMENTAL V2\n"
        "status: OK\n"
        f"market_files: {len(market_files)}\n"
        f"comparables_files: {len(comparable_files)}\n"
        f"report: {REPORT}\n\n",
        encoding="utf-8",
    )
    print(REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
