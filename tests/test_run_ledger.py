#!/usr/bin/env python3
"""Ledger contract tests.

Tests the Ledger protocol, not the application components. Every test named
test_regression_* corresponds to a defect in the first draft; see
CORRECTIONS.md.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gmv_run_ledger import (
    EVENT_SCHEMA,
    SATISFIED_STAGE_STATES,
    LedgerCorrupt,
    LockUnavailable,
    LedgerError,
    RunIdentity,
    RunLedger,
    RunLock,
    atomic_json_write,
    canonical_json_bytes,
    reduce_recorded_state,
)


COMPONENT = {
    "name": "test",
    "git_commit": "deadbeef",
    "git_dirty": False,
    "source_hash": None,
    "configuration_hash": "x",
    "stage_contract_version": 1,
}


def write_manifest(run_dir: Path, stages: list[str]) -> None:
    atomic_json_write(
        run_dir / "run_manifest.json",
        {
            "schema": "gmv.run-manifest.v0.1",
            "run_id": "RUN-TEST",
            "run_uuid": "test",
            "created_at": "2026-08-20T00:00:00.000Z",
            "pipeline": {
                "name": "test",
                "git_commit": "deadbeef",
                "git_dirty": False,
            },
            "host": {},
            "source": {"type": "fixture", "source_identity": "test"},
            "configuration": {"sha256": "x"},
            "component_source_sets": {},
            "stage_contract_versions": {s: 1 for s in stages},
            "requested_stages": stages,
        },
    )


class LedgerContractTests(unittest.TestCase):

    STAGES = ["10_EXTRACT", "20_ADAPT", "30_AUDIT"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / "RUN-TEST"
        self.run.mkdir()

        write_manifest(self.run, self.STAGES)

        self.ledger = RunLedger(self.run)
        self.ledger.lock.acquire()
        self.ledger.append_event(actor="gmv_pipeline", event_type="RUN_CREATED")
        self.ledger.append_event(actor="gmv_pipeline", event_type="RUN_STARTED")

    def tearDown(self):
        self.ledger.lock.release()
        self.tmp.cleanup()

    # -- helpers -----------------------------------------------------------

    def complete_stage(self, stage: str, filename: str) -> dict:
        self.ledger.append_event(
            actor="gmv_pipeline",
            event_type="STAGE_STARTED",
            stage=stage,
            component=COMPONENT,
        )

        path = self.run / filename
        path.write_text('{"value":1}\n', encoding="utf-8")

        artifact = self.ledger.register_artifact(
            actor="gmv_pipeline",
            stage=stage,
            artifact_type="ROWS",
            path=path,
            component=COMPONENT,
        )

        self.ledger.append_event(
            actor="gmv_pipeline",
            event_type="STAGE_COMPLETED",
            stage=stage,
            component=COMPONENT,
            input_artifacts=[],
            output_artifacts=[artifact["artifact_id"]],
        )
        return artifact

    # -- basic protocol ----------------------------------------------------

    def test_seq_is_contiguous(self):
        self.assertEqual(
            [e["seq"] for e in self.ledger.replay().events], [1, 2]
        )

    def test_every_event_carries_actor(self):
        for event in self.ledger.replay().events:
            self.assertIn("actor", event)

    def test_append_requires_lock(self):
        self.ledger.lock.release()
        with self.assertRaises(Exception):
            self.ledger.append_event(
                actor="gmv_pipeline", event_type="RUN_COMPLETED"
            )
        self.ledger.lock.acquire()

    def test_completed_run_cannot_resume(self):
        self.ledger.append_event(
            actor="gmv_pipeline", event_type="RUN_COMPLETED"
        )

        events = self.ledger.replay().events

        # Built outside the assertion block, with the correct next seq, so the
        # test can only pass because the reduction rejects the transition.
        illegal = {
            "schema": EVENT_SCHEMA,
            "seq": len(events) + 1,
            "run_id": "RUN-TEST",
            "timestamp": "2026-08-20T00:00:01.000Z",
            "event_type": "RUN_RESUMED",
            "actor": "gmv_pipeline",
        }

        with self.assertRaises(LedgerCorrupt):
            reduce_recorded_state(events + [illegal])

    def test_float_rejected_from_canonical_json(self):
        with self.assertRaises(Exception):
            canonical_json_bytes({"bad": 1.5})

    def test_bool_accepted_by_canonical_json(self):
        self.assertIn(b"true", canonical_json_bytes({"ok": True}))

    # -- artifacts ---------------------------------------------------------

    def test_artifact_without_registration_is_not_known(self):
        path = self.run / "artifacts"
        path.mkdir()
        (path / "rows.json").write_text("{}\n", encoding="utf-8")

        self.assertEqual(self.ledger.artifacts(), [])

    def test_artifact_registration_is_authoritative(self):
        artifact = self.complete_stage("10_EXTRACT", "rows.json")

        self.assertEqual(len(self.ledger.artifacts()), 1)

        valid, reason = self.ledger.verify_artifact(artifact)
        self.assertTrue(valid)
        self.assertIsNone(reason)

    def test_hash_mismatch_invalidates_checkpoint(self):
        self.complete_stage("10_EXTRACT", "rows.json")

        self.assertTrue(
            self.ledger.evaluate_checkpoint("10_EXTRACT")["valid"]
        )

        (self.run / "rows.json").write_text('{"value":2}\n', encoding="utf-8")

        projection = self.ledger.evaluate_checkpoint("10_EXTRACT")
        self.assertFalse(projection["valid"])
        self.assertTrue(
            any("HASH_MISMATCH" in c for c in projection["failed_conditions"])
        )

    # -- repair ------------------------------------------------------------

    def test_truncated_tail_is_ignored_then_repaired(self):
        with self.ledger.events_path.open("ab") as handle:
            handle.write(b'{"schema":"gmv.run-event.v0.1"')
            handle.flush()
            os.fsync(handle.fileno())

        self.assertGreater(self.ledger.replay(force=True).discarded_bytes, 0)

        event = self.ledger.repair_truncated_tail()
        self.assertEqual(event["event_type"], "LEDGER_REPAIRED")

        self.assertEqual(self.ledger.replay(force=True).discarded_bytes, 0)

    def test_append_behind_truncated_tail_is_rejected(self):
        with self.ledger.events_path.open("ab") as handle:
            handle.write(b'{"partial"')
            handle.flush()

        self.ledger.replay(force=True)

        with self.assertRaises(Exception):
            self.ledger.append_event(
                actor="gmv_pipeline", event_type="RUN_COMPLETED"
            )

    # -- regressions -------------------------------------------------------

    def test_regression_c3_corrupt_interior_under_truncated_tail(self):
        """C-3: the draft skipped sequence validation when the tail was
        truncated, so an interior corruption replayed as clean."""
        with self.ledger.events_path.open("ab") as handle:
            handle.write(b'{"not":"an event"}\n')   # complete but invalid
            handle.write(b'{"truncated"')           # partial final record
            handle.flush()

        with self.assertRaises(LedgerCorrupt):
            self.ledger.replay(force=True)

    def test_non_object_record_is_reported_as_ledger_corruption(self):
        with self.ledger.events_path.open("ab") as handle:
            handle.write(b"[]\n")

        with self.assertRaisesRegex(LedgerCorrupt, "must be a JSON object"):
            self.ledger.replay(force=True)

    def test_regression_c8_skipped_stage_is_a_satisfied_boundary(self):
        """C-8: a skipped stage must not force recomputation of everything."""
        self.ledger.append_event(
            actor="gmv_pipeline",
            event_type="STAGE_SKIPPED",
            stage="10_EXTRACT",
            reason="TEST",
        )
        self.complete_stage("20_ADAPT", "adapted.json")

        stages = self.ledger.recorded_state()["stages"]
        self.assertIn(stages["10_EXTRACT"], SATISFIED_STAGE_STATES)

        skipped = self.ledger.evaluate_checkpoint("10_EXTRACT")
        self.assertTrue(skipped["valid"])
        self.assertEqual(skipped["resume_from"], "20_ADAPT")

        adapted = self.ledger.evaluate_checkpoint("20_ADAPT")
        self.assertTrue(adapted["valid"])
        self.assertEqual(adapted["resume_from"], "30_AUDIT")


class InterruptedClassificationTests(unittest.TestCase):
    """C-9: a Run crashed before RUN_STARTED must remain classifiable."""

    def test_regression_c9_created_can_be_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN-TEST"
            run.mkdir()
            write_manifest(run, ["10_EXTRACT"])

            ledger = RunLedger(run)
            ledger.lock.acquire()
            ledger.append_event(
                actor="gmv_pipeline", event_type="RUN_CREATED"
            )
            ledger.lock.release()

            # A second process inspects the abandoned Run.
            inspector = RunLedger(run)
            inspector.lock.acquire()
            try:
                self.assertEqual(
                    inspector.recorded_state()["run_state"], "CREATED"
                )
                inspector.append_event(
                    actor="gmv_recovery",
                    event_type="RUN_INTERRUPTED",
                    observed={"recorded_state": "CREATED"},
                )
                self.assertEqual(
                    inspector.recorded_state()["run_state"], "INTERRUPTED"
                )
            finally:
                inspector.lock.release()


class RunIdentityTests(unittest.TestCase):
    def test_dirty_source_hash_is_an_immutable_snapshot(self):
        identity = RunIdentity(
            repo_root=Path("/unused"),
            git_commit="deadbeef",
            git_dirty=True,
            config_hash="config",
            source_hashes={("component.py",): "captured-hash"},
        )

        fingerprint = identity.fingerprint(
            component_name="component",
            source_set=["component.py"],
            stage_contract_version=1,
        )

        self.assertEqual(fingerprint["source_hash"], "captured-hash")

    def test_dirty_uncaptured_source_set_is_rejected(self):
        identity = RunIdentity(
            repo_root=Path("/unused"),
            git_commit="deadbeef",
            git_dirty=True,
            config_hash="config",
        )

        with self.assertRaisesRegex(LedgerError, "was not captured"):
            identity.fingerprint(
                component_name="component",
                source_set=["component.py"],
                stage_contract_version=1,
            )


class LockInheritanceTests(unittest.TestCase):
    """C-1: release() must close the descriptor, never issue LOCK_UN.

    An flock belongs to the open file description, shared with every child
    that inherited the descriptor. LOCK_UN releases it for all of them, which
    destroys the B2 guarantee that an orphaned child keeps the Run locked.
    """

    CHILD = "import os, sys, time; os.fstat(int(sys.argv[1])); time.sleep(3)"

    def test_child_keeps_flock_after_parent_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "run.lock"

            parent = RunLock(lock_path)
            parent.acquire()

            child = subprocess.Popen(  # noqa: S603 - fixed test interpreter
                [sys.executable, "-c", self.CHILD, str(parent.fd)],
                pass_fds=(parent.fd,),
            )

            time.sleep(0.3)
            parent.release()

            competing = RunLock(lock_path)
            with self.assertRaises(LockUnavailable):
                competing.acquire()

            child.wait(timeout=10)

            # Last inherited descriptor closed -> the kernel frees the lock.
            competing.acquire()
            competing.release()

    def test_second_acquire_on_same_object_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = RunLock(Path(tmp) / "run.lock")
            lock.acquire()
            try:
                with self.assertRaises(Exception):
                    lock.acquire()
            finally:
                lock.release()


if __name__ == "__main__":
    unittest.main(verbosity=2)
