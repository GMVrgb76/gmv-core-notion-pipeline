# OpenCode Task 40 — wire Task 38's Notion export and Task 39's date extraction into the existing 07:00 gbrain sync

**Status: DRAFT TASK.**

## Why

`~/.gmv_scripts/gbrain_morning_sync.sh`, scheduled daily at 07:00 by
`~/Library/LaunchAgents/com.gmv.gbrain.morningsync.plist` (confirmed real and running — `Hour: 7,
Minute: 0`), already re-imports `03_STATE/area35_canon/*.md` into gbrain every morning. But nothing
ever refreshes those files from the live Notion database, and nothing ever re-runs the date
extraction into gbrain's timeline. Today's work built both pieces as one-off manual runs:

- Task 38: `10_API/gmv_notion_canon_export.py` — reads the real Area35 Notion workspace, writes/
  overwrites `03_STATE/area35_canon/<page_id>.md`, one file per real page.
- Task 39: `10_API/gmv_area35_canon_timeline.py` — reads those canon files, writes exhibition dates
  into gbrain's timeline via `gbrain timeline-add` (confirmed: needs `gbrain serve` stopped, and is
  idempotent on replay — see that file's own module docstring and today's commit history,
  `9a3f2b05`/`4eaeb0f4`/`e0cca264`, for the full empirical findings already made).

**The ask, plainly stated by the human:** if a Notion card is added or edited, the existing daily
job should pick it up automatically — no one should have to remember to re-run either script by
hand again. This is wiring three already-working, already-tested pieces together, not building
anything new.

## What changes, concretely

Edit `~/.gmv_scripts/gbrain_morning_sync.sh` (the real, live, already-scheduled script — read it in
full first, do not reconstruct it from this brief's summary) to add two new steps:

1. **Before** the existing `pkill -f "gbrain serve --http"` line: run
   `10_API/gmv_notion_canon_export.py` with its real credentials (`--config
   ~/.gmv_core/area35-qa/config.json --token-file ~/.config/area35-qa/notion_token`, confirmed
   working paths from today — re-verify they're still valid, don't assume). This step talks only to
   the Notion API and the local filesystem; it does **not** touch gbrain, so it does not need
   `gbrain serve` stopped — keep it outside the stop/restart window, not inside it, so the server
   stays up for the shortest time possible.
2. **After** the existing `SOURCE_DIRS` import loop, still inside the existing stopped-server
   window (before the `nohup ... serve --http` restart line): run `10_API/gmv_area35_canon_timeline.py
   --apply --source default` (confirm the real current CLI flags by reading that file's `argparse`
   setup directly — today's brief used `--apply` and `--source`, but read the real current signature,
   don't trust this summary).

## Constraints

1. **Do not break the existing Dropbox-constitution import** (the first `SOURCE_DIRS` entry,
   unrelated to Area35/Notion) — it must keep running exactly as it does today regardless of
   whether the new Notion-export step succeeds or fails.
2. **A failure in the new export step must not leave gbrain down or skip the existing imports.**
   The script already has no `set -e`; keep that property — one step's failure should log and
   continue, not abort the whole sync. Specifically: if `gmv_notion_canon_export.py` fails (Notion
   API down, bad token, rate limit), the script must still proceed to stop/import/restart gbrain
   with whatever canon files are already on disk from the last successful run — never leave the
   server down because an earlier, unrelated step failed.
3. **The server-down window must still end with `gbrain serve` running**, exactly as today's
   script already guarantees (the existing `pgrep` check + WARNING log) — the new timeline-apply
   step sits inside that window, so if it hangs or errors, the restart logic must still fire
   afterward, not be skipped.
4. **Log clearly which of the (now four) steps ran, succeeded, or failed**, in the same
   `$LOG_FILE` (`~/.gbrain/logs/morning_sync.log`), same `log()` helper, same timestamp style —
   don't introduce a second logging convention.
5. **Do not change the LaunchAgent plist** — the schedule (07:00 daily) is already correct and
   already real; this task only changes the script it calls.
6. Keep `GBRAIN_ADMIN_BOOTSTRAP_TOKEN` read-fresh-from-`~/.zshrc` behavior exactly as today —
   don't duplicate or hardcode it.
7. **Every command this script runs must be non-interactive, with zero exceptions.** `launchd`
   invokes this at 07:00 with no terminal and no human present — any command that would otherwise
   wait on a confirmation prompt (today's session hit exactly this pattern on other `gbrain`
   subcommands needing an explicit `--yes`/`--json`/non-interactive flag to avoid one) will hang
   the job forever, silently, with nobody there to answer it. Explicitly check the real current
   `gmv_notion_canon_export.py`, `gmv_area35_canon_timeline.py`, and every `gbrain` subcommand this
   script calls (`import`, `timeline-add`, `serve`) for any interactive/confirmation path and pass
   whatever flag suppresses it. Prove this empirically, not by reading flags and assuming: run the
   final script with stdin redirected from `/dev/null` (`< /dev/null`) so any accidental prompt
   fails fast with an EOF/read error in the log instead of hanging — a hang in this test is a bug
   to fix, not a result to report and move past.

## Verification required before calling this done

1. **Run the modified script manually once** (not by waiting for 07:00 or touching the
   LaunchAgent) and confirm, in order: the Notion export ran and reported real counts (compare
   against today's known baseline, 442 pages / 95 events, re-derive don't assume); the existing
   Dropbox + canon imports still ran; the timeline extractor ran and reported its real apply count;
   `gbrain serve` is up and healthy afterward (`curl http://localhost:3131/health`).
2. **Test the failure-tolerance constraint for real**, not just by reading the code: temporarily
   point the export step at a bad token or unreachable config (your choice how, revert after),
   confirm the script still completes the Dropbox/canon imports and still leaves `gbrain serve`
   running, then restore the real config and re-run once clean.
3. Confirm one real timeline entry is unchanged/still correct after a full manual run (replay
   idempotency, already proven for the timeline step alone today — now prove it survives inside
   the combined script).
4. Run the final script once with `< /dev/null` (no stdin at all, simulating exactly how `launchd`
   invokes it) and confirm it completes end-to-end with no hang — this is the real test for
   constraint 7, not optional.

## Report back

1. The real final diff of `gbrain_morning_sync.sh`.
2. Output of the one real manual end-to-end run: counts from each of the three/four steps, final
   `gbrain serve` health check result.
3. What happened in the deliberate failure-injection test, and confirmation the script still left
   gbrain running afterward.
4. Anything about the real current `gmv_notion_canon_export.py` or `gmv_area35_canon_timeline.py`
   CLI signatures that differed from what this brief assumed.
