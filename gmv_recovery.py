#!/usr/bin/env python3
"""GMV Run recovery inspector — contract v0.1.2.

Observes and classifies. It never resumes: the resume decision belongs to
gmv_pipeline.py --resume, which is not yet implemented.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gmv_run_ledger import (
    LEDGER_ROOT,
    SATISFIED_STAGE_STATES,
    LedgerCorrupt,
    LockUnavailable,
    RunLedger,
    verify_substrate,
)

TERMINAL_STATES = {"COMPLETED", "ABORTED"}

# [C-9] The draft classified only RUNNING. A crash between RUN_CREATED and
# RUN_STARTED left the Run in CREATED forever: unclassifiable, permanently in
# _active, with no path out. §18 must gain the CREATED -> INTERRUPTED row.
CLASSIFIABLE_STATES = {"CREATED", "RUNNING"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Inspect and classify unfinished GMV Runs."
    )
    parser.add_argument("--ledger-root", type=Path, default=LEDGER_ROOT)
    parser.add_argument("--run-id", help="Inspect one Run; default is _active.")
    return parser.parse_args()


def inspect_run(run_dir: Path) -> dict:
    if not run_dir.is_dir() or not (run_dir / "run_manifest.json").is_file():
        return {
            "run_id": run_dir.name,
            "canonical_state": "NOT_FOUND",
            "action": "DO_NOT_RESUME",
            "error": f"Run directory or manifest not found: {run_dir}",
        }

    ledger = RunLedger(run_dir)

    # §42 step 3-4: no event is written for a Run this process does not own.
    try:
        ledger.lock.acquire()
    except LockUnavailable:
        return {
            "run_id": run_dir.name,
            "canonical_state": "RUNNING",
            "live": True,
            "action": "DO_NOT_RESUME",
            "note": (
                "Lock held by a live process, or by an orphaned child that "
                "inherited the descriptor."
            ),
        }

    try:
        # §42 ordering: repair the tail before writing any classification.
        if ledger.replay().discarded_bytes:
            ledger.repair_truncated_tail()

        recorded = ledger.recorded_state()["run_state"]

        if recorded in CLASSIFIABLE_STATES:
            events = ledger.replay().events
            ledger.append_event(
                actor="gmv_recovery",
                event_type="RUN_INTERRUPTED",
                observed={
                    "recorded_state": recorded,
                    "last_committed_seq": events[-1]["seq"] if events else 0,
                    "lock_acquired": True,
                    "prior_host": ledger.manifest.get("host"),
                },
            )
            recorded = ledger.recorded_state()["run_state"]

        return build_report(ledger, recorded)

    except LedgerCorrupt as exc:
        return {
            "run_id": run_dir.name,
            "canonical_state": "LEDGER_CORRUPT",
            "action": "DO_NOT_RESUME",
            "error": str(exc),
        }

    finally:
        ledger.lock.release()


def build_report(ledger: RunLedger, recorded_state: str) -> dict:
    manifest = ledger.manifest
    requested = manifest["requested_stages"]
    stages = ledger.recorded_state()["stages"]

    # [C-8] Walk requested stages in order and stop at the first boundary that
    # is not satisfied. Two corrections in one:
    #
    #   - SKIPPED counts as satisfied. The draft required COMPLETED, so a Run
    #     with a skipped stage always reported resume_from = requested[0] and
    #     demanded a full recomputation of stages that had verified.
    #
    #   - Stopping at the first failure. The draft took valid_completed[-1],
    #     so a later valid stage after an earlier invalid one was treated as a
    #     resume point, skipping over a boundary known to be broken.
    checkpoints: dict[str, dict] = {}
    last_satisfied: str | None = None

    for stage in requested:
        if stages.get(stage, "NOT_STARTED") not in SATISFIED_STAGE_STATES:
            break

        projection = ledger.evaluate_checkpoint(stage)
        checkpoints[stage] = projection

        if not projection["valid"]:
            break

        last_satisfied = stage

    if last_satisfied is None:
        resume_from = requested[0] if requested else None
    else:
        index = requested.index(last_satisfied)
        resume_from = requested[index + 1] if index + 1 < len(requested) else None

    if resume_from is None:
        recomputation = {stage: False for stage in requested}
    else:
        boundary = requested.index(resume_from)
        recomputation = {
            stage: (position >= boundary)
            for position, stage in enumerate(requested)
        }

    artifacts = []
    for artifact in ledger.artifacts():
        valid, reason = ledger.verify_artifact(artifact)
        artifacts.append(
            {
                "artifact_id": artifact["artifact_id"],
                "type": artifact["artifact_type"],
                "path": artifact["path"],
                "valid": valid,
                "reason": reason,
            }
        )

    completed = [s for s in requested if stages.get(s) == "COMPLETED"]
    running = [s for s in requested if stages.get(s) == "RUNNING"]

    return {
        "run_id": manifest["run_id"],
        "canonical_state": recorded_state,
        "live": False,
        "requested_stages": requested,
        "stage_states": {s: stages.get(s, "NOT_STARTED") for s in requested},
        "interrupted_stage": running[-1] if running else None,
        "last_completed_stage": completed[-1] if completed else None,
        "last_valid_checkpoint": last_satisfied,
        "resume_from": resume_from,
        "recomputation_required": recomputation,
        "artifacts": artifacts,
        "checkpoints": checkpoints,
        "action": (
            "NO_ACTION"
            if recorded_state in TERMINAL_STATES
            else "RESUME_AVAILABLE" if resume_from else "FINALIZE_AVAILABLE"
        ),
    }


def render_text(report: dict) -> str:
    """Human-readable form of §43. Derived entirely from the manifest."""
    lines = [
        "RUN", report["run_id"], "",
        "STATE", report["canonical_state"], "",
    ]

    if report.get("live"):
        lines += ["ACTION", report["action"], "", report.get("note", "")]
        return "\n".join(lines)

    if "requested_stages" not in report:
        lines += [
            "ACTION", report.get("action", "DO_NOT_RESUME"), "",
            "ERROR", report.get("error", "Unknown recovery error"),
        ]
        return "\n".join(lines)

    lines += [
        "REQUESTED STAGES",
        *[f"{s:<24}{report['stage_states'][s]}"
          for s in report["requested_stages"]],
        "",
        "LAST COMPLETED STAGE",
        str(report["last_completed_stage"]),
        "",
        "LAST VALID CHECKPOINT",
        str(report["last_valid_checkpoint"]),
        "",
        "RESUME FROM",
        str(report["resume_from"]),
        "",
        "ARTIFACT STATUS",
        *[f"{a['path']:<40}{'VALID' if a['valid'] else a['reason']}"
          for a in report["artifacts"]],
        "",
        "RECOMPUTATION REQUIRED",
        *[f"{s:<24}{'YES' if report['recomputation_required'][s] else 'NO'}"
          for s in report["requested_stages"]],
    ]

    return "\n".join(lines)


def active_runs(root: Path) -> list[Path]:
    active = root / "_active"
    if not active.exists():
        return []

    root_resolved = root.resolve()
    runs = []
    for entry in sorted(active.iterdir()):
        try:
            run_dir = entry.resolve(strict=True)
            run_dir.relative_to(root_resolved)
        except (FileNotFoundError, OSError):
            continue  # dangling _active entry; the Run directory is gone
        except ValueError:
            continue  # _active must never escape the configured Ledger root
        if run_dir.is_dir() and (run_dir / "run_manifest.json").is_file():
            runs.append(run_dir)
    return runs


def main() -> int:
    args = parse_args()
    root = args.ledger_root.expanduser()

    verify_substrate(root)

    run_dirs = [root / args.run_id] if args.run_id else active_runs(root)
    reports = [inspect_run(run_dir) for run_dir in run_dirs]

    print(json.dumps(reports, ensure_ascii=False, indent=2))

    for report in reports:
        print("\n" + "-" * 60, file=sys.stderr)
        print(render_text(report), file=sys.stderr)

    return 2 if any(
        report.get("canonical_state") in {"LEDGER_CORRUPT", "NOT_FOUND"}
        for report in reports
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
