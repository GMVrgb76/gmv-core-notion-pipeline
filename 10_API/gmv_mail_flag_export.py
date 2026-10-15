#!/usr/bin/env python3
"""Export flagged Apple Mail messages (and one Proton label folder) as .eml into inbox/mail.

Reads Mail.app through AppleScript; never modifies flags, folders or messages.
Already-exported messages are recognised by a hash of their Message-ID.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SKIP_MAILBOXES = ["All Mail", "Trash", "Spam", "Junk", "Drafts", "Deleted Messages", "Bin"]

LIST_SCRIPT = """
on run argv
  set flagIdx to (item 1 of argv) as integer
  set labelAcct to item 2 of argv
  set labelBox to item 3 of argv
  set skipNames to {%s}
  set out to ""
  tell application "Mail"
    repeat with a in accounts
      set an to name of a
      set boxes to every mailbox of a
      repeat with i from 1 to count of boxes
        set m to item i of boxes
        set mn to name of m
        if mn is not in skipNames then
          set wanted to {}
          try
            if an is labelAcct and mn is labelBox then
              set wanted to messages of m
            else
              set wanted to (messages of m whose flag index is flagIdx)
            end if
          end try
          repeat with msg in wanted
            set mid to ""
            try
              set mid to message id of msg
            end try
            set out to out & an & tab & i & tab & (id of msg) & tab & mid & linefeed
          end repeat
        end if
      end repeat
    end repeat
  end tell
  return out
end run
""" % ", ".join('"%s"' % n for n in SKIP_MAILBOXES)

EXPORT_SCRIPT = """
on run argv
  set acctName to item 1 of argv
  set boxIdx to (item 2 of argv) as integer
  set msgId to (item 3 of argv) as integer
  set outPath to item 4 of argv
  tell application "Mail"
    set m to item boxIdx of (every mailbox of account acctName)
    set msg to first message of m whose id is msgId
    set src to source of msg
  end tell
  set fp to open for access (POSIX file outPath) with write permission
  try
    set eof of fp to 0
    write src to fp as «class utf8»
  end try
  close access fp
end run
"""

Runner = Callable[[str, list[str]], str]


@dataclass(frozen=True)
class Candidate:
    account: str
    mailbox_index: int
    message_id: int
    header_id: str

    @property
    def key(self) -> str:
        ident = self.header_id.strip().strip("<>")
        return ident or f"{self.account}|{self.mailbox_index}|{self.message_id}"

    @property
    def filename(self) -> str:
        return hashlib.sha1(self.key.encode("utf-8"), usedforsecurity=False).hexdigest()[:16] + ".eml"


def osascript_runner(script: str, args: list[str]) -> str:
    result = subprocess.run(  # noqa: S603  # gmv-floor-ok: fixed /usr/bin/osascript argv, no shell, script is a module constant
        ["/usr/bin/osascript", "-", *args], input=script, text=True, capture_output=True, timeout=600
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"osascript rc={result.returncode}")
    return result.stdout


def parse_candidates(output: str) -> list[Candidate]:
    found: dict[str, Candidate] = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        header_id = parts[3] if len(parts) > 3 else ""
        cand = Candidate(parts[0], int(parts[1]), int(parts[2]), header_id)
        found.setdefault(cand.key, cand)
    return list(found.values())


def run(
    dest: Path,
    flag_index: int,
    label_account: str,
    label_mailbox: str,
    dry_run: bool = False,
    runner: Runner = osascript_runner,
) -> dict[str, int]:
    stats = {"candidates": 0, "exported": 0, "already_exported": 0, "errors": 0}
    candidates = parse_candidates(runner(LIST_SCRIPT, [str(flag_index), label_account, label_mailbox]))
    stats["candidates"] = len(candidates)
    dest.mkdir(parents=True, exist_ok=True)
    for cand in candidates:
        target = dest / cand.filename
        if target.exists():
            stats["already_exported"] += 1
            continue
        if dry_run:
            stats["exported"] += 1
            continue
        partial = target.with_suffix(".eml.part")
        try:
            runner(EXPORT_SCRIPT, [cand.account, str(cand.mailbox_index), str(cand.message_id), str(partial)])
            if not partial.exists() or partial.stat().st_size == 0:
                raise RuntimeError("empty export")
            partial.rename(target)
            stats["exported"] += 1
        except Exception as exc:
            partial.unlink(missing_ok=True)
            stats["errors"] += 1
            print(f"ERROR {cand.account}#{cand.message_id}: {exc}", file=sys.stderr)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", type=Path, required=True, help="inbox/mail folder")
    ap.add_argument("--flag-index", type=int, default=4, help="Mail flag colour: 0 red, 1 orange, 2 yellow, 3 green, 4 blue, 5 purple, 6 gray")
    ap.add_argument("--label-account", default="", help="Mail account whose label folder is exported entirely")
    ap.add_argument("--label-mailbox", default="EXPORT")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    stats = run(args.dest, args.flag_index, args.label_account, args.label_mailbox, args.dry_run)
    print(json.dumps(stats))
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
