#!/usr/bin/env python3
"""GMV Core pipeline wrapper — Run Ledger contract v0.1.2.

Wraps the existing components without modifying them. Corrections against the
first draft are marked [C-n]; see CORRECTIONS.md.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from gmv_run_ledger import (
    LEDGER_ROOT,
    RunIdentity,
    RunLedger,
    create_run,
    deactivate_run,
)


STAGES = [
    "10_EXTRACT",
    "20_ADAPT",
    "30_AUDIT",
    "40_REMEDIATION_PLAN",
    "80_FINALIZE",
]

VERSIONS = {
    "10_EXTRACT": 1,
    "20_ADAPT": 1,
    "30_AUDIT": 1,
    "40_REMEDIATION_PLAN": 1,
    "80_FINALIZE": 1,
}

SOURCE_SETS = {
    "notion_extract": ["notion_extract.py"],
    "pipeline_rows_ingest": ["gmv_pipeline.py"],
    "area35_validator": ["area35_validator.py"],
    "gmv_remediator": ["gmv_remediator.py", "remediation_rules.json"],
    "gmv_pipeline": ["gmv_pipeline.py", "gmv_run_ledger.py"],
}

# Exit codes [C-13]
EXIT_CLEAN = 0
EXIT_BLOCKERS = 1
EXIT_PIPELINE_FAILURE = 2


def parse_args():
    parser = argparse.ArgumentParser(
        description="GMV Core pipeline with Run Ledger v0.1.2"
    )
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--rows", type=Path)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Path("~/.config/area35-qa/notion_token").expanduser(),
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--entities")
    parser.add_argument("--ledger-root", type=Path, default=LEDGER_ROOT)
    return parser.parse_args()


def run_child(
    ledger: RunLedger,
    command: list[str],
    *,
    stdout_path: Path,
    accepted_codes: frozenset[int] = frozenset({0}),
) -> int:
    """Execute a component, passing the Run lock descriptor to the child.

    pass_fds is the B2 requirement: the child inherits the open file
    description that holds the flock, so an orphaned child keeps the Run
    locked after this wrapper dies.
    """
    if ledger.lock.fd is None:
        raise RuntimeError("Run lock is not held.")

    stdout_path.parent.mkdir(parents=True, exist_ok=True)

    with stdout_path.open("ab") as output:
        process = subprocess.Popen(  # noqa: S603 - argv only, never a shell
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            pass_fds=(ledger.lock.fd,),
        )
        return_code = process.wait()

    if return_code not in accepted_codes:
        raise subprocess.CalledProcessError(return_code, command)

    return return_code


def count_rows(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return sum(len(v) for v in payload.values() if isinstance(v, list))
    return 0


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def stage_extract(ledger, identity, repo, args) -> tuple[dict, Path]:
    """10_EXTRACT — either run the extractor, or ingest external rows.

    [C-12] The stage records the component that actually executes. When rows
    are supplied with --rows, the ingest is performed by this wrapper, so the
    fingerprint names gmv_pipeline.py, not notion_extract.py.
    """
    out = ledger.run_dir / "artifacts" / "extract" / "rows.json"

    if args.extract:
        component_name = "notion_extract"
    else:
        if not args.rows:
            raise RuntimeError("Use --extract or provide --rows FILE.")
        component_name = "pipeline_rows_ingest"

    component = identity.fingerprint(
        component_name=component_name,
        source_set=SOURCE_SETS[component_name],
        stage_contract_version=VERSIONS["10_EXTRACT"],
    )

    ledger.append_event(
        actor="gmv_pipeline",
        event_type="STAGE_STARTED",
        stage="10_EXTRACT",
        component=component,
    )

    if args.extract:
        command = [
            sys.executable,
            str(repo / "notion_extract.py"),
            "--config", str(args.config),
            "--out", str(out),
            "--token-file", str(args.token_file),
        ]
        if args.limit:
            command += ["--limit", str(args.limit)]
        if args.entities:
            command += ["--entities", args.entities]

        run_child(
            ledger, command, stdout_path=ledger.run_dir / "logs" / "extract.log"
        )
    else:
        # The external file is copied into the Run so that every registered
        # artifact lives inside the Run directory and is hash-verifiable.
        shutil.copy2(args.rows.resolve(), out)

    artifact = ledger.register_artifact(
        actor="gmv_pipeline",
        stage="10_EXTRACT",
        artifact_type="ROWS_NORMALIZED",
        path=out,
        component=component,
        record_count=count_rows(out),
    )

    ledger.append_event(
        actor="gmv_pipeline",
        event_type="STAGE_COMPLETED",
        stage="10_EXTRACT",
        component=component,
        input_artifacts=[],
        output_artifacts=[artifact["artifact_id"]],
        source_mode="NOTION_EXTRACT" if args.extract else "EXTERNAL_ROWS",
    )

    return artifact, out


def stage_adapt(ledger) -> None:
    """20_ADAPT — skipped.

    [C-12] notion_extract.py already emits the normalized rows contract the
    validator consumes. The draft copied the file and attributed the stage to
    adapter_notion.py, which never ran: a false code identity under §34, and a
    duplicated copy of the rows for no analytical gain.

    The stage is reserved for the day an actual adaptation step exists.
    """
    ledger.append_event(
        actor="gmv_pipeline",
        event_type="STAGE_SKIPPED",
        stage="20_ADAPT",
        reason="EXTRACTOR_EMITS_NORMALIZED_ROWS",
    )


def stage_audit(ledger, identity, repo, args, rows_artifact, rows_path):
    component = identity.fingerprint(
        component_name="area35_validator",
        source_set=SOURCE_SETS["area35_validator"],
        stage_contract_version=VERSIONS["30_AUDIT"],
    )

    ledger.append_event(
        actor="gmv_pipeline",
        event_type="STAGE_STARTED",
        stage="30_AUDIT",
        component=component,
    )

    report_dir = ledger.run_dir / "artifacts" / "audit" / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    # Exit code 1 means BLOCKER found: a valid epistemic result of the audit,
    # not a component crash.
    audit_code = run_child(
        ledger,
        [
            sys.executable,
            str(repo / "area35_validator.py"),
            "--config", str(args.config),
            "--rows", str(rows_path),
            "--out", str(report_dir),
        ],
        stdout_path=ledger.run_dir / "logs" / "audit.log",
        accepted_codes=frozenset({0, 1}),
    )

    issues_path = report_dir / "issues.json"
    issues = json.loads(issues_path.read_text(encoding="utf-8"))

    artifact = ledger.register_artifact(
        actor="gmv_pipeline",
        stage="30_AUDIT",
        artifact_type="ISSUES",
        path=issues_path,
        component=component,
        input_artifacts=[rows_artifact["artifact_id"]],
        record_count=len(issues) if isinstance(issues, list) else None,
    )

    ledger.append_event(
        actor="gmv_pipeline",
        event_type="STAGE_COMPLETED",
        stage="30_AUDIT",
        component=component,
        input_artifacts=[rows_artifact["artifact_id"]],
        output_artifacts=[artifact["artifact_id"]],
        result={
            "validator_exit_code": audit_code,
            "blocker_gate_triggered": audit_code == 1,
        },
    )

    return artifact, issues_path, audit_code


def stage_remediation_plan(ledger, identity, repo, issues_artifact, issues_path):
    component = identity.fingerprint(
        component_name="gmv_remediator",
        source_set=SOURCE_SETS["gmv_remediator"],
        stage_contract_version=VERSIONS["40_REMEDIATION_PLAN"],
    )

    ledger.append_event(
        actor="gmv_pipeline",
        event_type="STAGE_STARTED",
        stage="40_REMEDIATION_PLAN",
        component=component,
    )

    plan = ledger.run_dir / "artifacts" / "remediation" / "plan.json"

    run_child(
        ledger,
        [
            sys.executable,
            str(repo / "gmv_remediator.py"),
            "analyze",
            "--issues", str(issues_path),
            "--rules", str(repo / "remediation_rules.json"),
            "--plan", str(plan),
        ],
        stdout_path=ledger.run_dir / "logs" / "remediator.log",
    )

    artifact = ledger.register_artifact(
        actor="gmv_pipeline",
        stage="40_REMEDIATION_PLAN",
        artifact_type="REMEDIATION_PLAN",
        path=plan,
        component=component,
        input_artifacts=[issues_artifact["artifact_id"]],
    )

    ledger.append_event(
        actor="gmv_pipeline",
        event_type="STAGE_COMPLETED",
        stage="40_REMEDIATION_PLAN",
        component=component,
        input_artifacts=[issues_artifact["artifact_id"]],
        output_artifacts=[artifact["artifact_id"]],
    )

    return artifact


def stage_finalize(ledger, identity, rows_artifact, issues_artifact,
                   plan_artifact, audit_code) -> None:
    component = identity.fingerprint(
        component_name="gmv_pipeline",
        source_set=SOURCE_SETS["gmv_pipeline"],
        stage_contract_version=VERSIONS["80_FINALIZE"],
    )

    ledger.append_event(
        actor="gmv_pipeline",
        event_type="STAGE_STARTED",
        stage="80_FINALIZE",
        component=component,
    )

    inputs = [
        rows_artifact["artifact_id"],
        issues_artifact["artifact_id"],
        plan_artifact["artifact_id"],
    ]

    summary_path = ledger.run_dir / "artifacts" / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "run_id": ledger.manifest["run_id"],
                "rows_artifact": rows_artifact["artifact_id"],
                "issues_artifact": issues_artifact["artifact_id"],
                "remediation_plan_artifact": plan_artifact["artifact_id"],
                "validator_exit_code": audit_code,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    artifact = ledger.register_artifact(
        actor="gmv_pipeline",
        stage="80_FINALIZE",
        artifact_type="RUN_SUMMARY",
        path=summary_path,
        component=component,
        input_artifacts=inputs,
    )

    ledger.append_event(
        actor="gmv_pipeline",
        event_type="STAGE_COMPLETED",
        stage="80_FINALIZE",
        component=component,
        input_artifacts=inputs,
        output_artifacts=[artifact["artifact_id"]],
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_pipeline(*, ledger, identity, repo, args) -> int:
    """Returns the validator exit code so main() can propagate the gate."""
    rows_artifact, rows_path = stage_extract(ledger, identity, repo, args)

    stage_adapt(ledger)

    issues_artifact, issues_path, audit_code = stage_audit(
        ledger, identity, repo, args, rows_artifact, rows_path
    )

    plan_artifact = stage_remediation_plan(
        ledger, identity, repo, issues_artifact, issues_path
    )

    stage_finalize(
        ledger, identity, rows_artifact, issues_artifact,
        plan_artifact, audit_code,
    )

    return audit_code


def main() -> int:
    args = parse_args()

    repo = Path(__file__).resolve().parent
    args.config = args.config.resolve()

    # [C-6] Code and configuration identity are captured once, before the Run
    # exists. Recomputing them per stage let a mid-run edit produce two
    # different fingerprints inside one Run, which silently corrupts the
    # intra-run resume comparison of §35 Rule 2.
    identity = RunIdentity.capture(repo, args.config, SOURCE_SETS)

    ledger = create_run(
        identity=identity,
        requested_stages=STAGES,
        source_identity="area35",
        config_path=args.config,
        component_source_sets=SOURCE_SETS,
        stage_contract_versions=VERSIONS,
        ledger_root=args.ledger_root,
    )

    try:
        audit_code = run_pipeline(
            ledger=ledger, identity=identity, repo=repo, args=args
        )

        ledger.append_event(actor="gmv_pipeline", event_type="RUN_COMPLETED")
        deactivate_run(ledger.manifest["run_id"], args.ledger_root)

        # [C-13] The draft always returned 0, so a caller could not tell an
        # audit that found blockers from a clean one.
        return EXIT_BLOCKERS if audit_code == 1 else EXIT_CLEAN

    # [C-14] Deliberately Exception, not BaseException: KeyboardInterrupt and
    # SIGKILL must leave the Run RUNNING so gmv_recovery classifies it as
    # INTERRUPTED. Only handled failures become RUN_FAILED.
    except Exception as exc:
        _record_failure(ledger, exc)
        print(f"[GMV Ledger] pipeline failed: {exc}", file=sys.stderr)
        return EXIT_PIPELINE_FAILURE

    finally:
        # Releasing closes this process's descriptor only. If a child is still
        # alive it retains the inherited description and the Run stays locked.
        ledger.lock.release()


def _record_failure(ledger: RunLedger, exc: BaseException) -> None:
    error = {"type": type(exc).__name__, "message": str(exc)}

    try:
        stages = ledger.recorded_state()["stages"]
        current = next(
            (s for s, status in stages.items() if status == "RUNNING"), None
        )
        if current:
            ledger.append_event(
                actor="gmv_pipeline",
                event_type="STAGE_FAILED",
                stage=current,
                error=error,
            )
    except Exception as record_error:
        print(
            f"[GMV Ledger] could not record stage failure: {record_error}",
            file=sys.stderr,
        )

    try:
        ledger.append_event(
            actor="gmv_pipeline", event_type="RUN_FAILED", error=error
        )
    except Exception as record_error:
        print(
            f"[GMV Ledger] could not record Run failure: {record_error}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    raise SystemExit(main())
