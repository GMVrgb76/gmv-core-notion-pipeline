from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gmv_remediator as remediator
import area35_validator as validator


ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "remediation_rules.json"


def dump(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def issue(code="R03", message="Relazione asimmetrica: 'Artista A' non riporta 'Opera A' in 'opere'."):
    return {
        "codice": code,
        "severita": "MINOR",
        "entita": "opera",
        "record_id": "work-1",
        "titolo": "Opera A",
        "campo": "artista",
        "messaggio": message,
        "azione": "",
    }


def fixture():
    rows = {
        "artista": [
            {
                "id": "artist-1",
                "titolo": "Artista A",
                "campi": {"nome": "Artista A"},
                "relazioni": {"opere": []},
                "servizio": {},
                "corpo": "",
            }
        ],
        "opera": [
            {
                "id": "work-1",
                "titolo": "Opera A",
                "campi": {"titolo": "Opera A"},
                "relazioni": {"artista": ["artist-1"]},
                "servizio": {},
            }
        ],
    }
    config = {
        "entita": {
            "artista": {
                "relazioni": {
                    "opere": {"target": "opera", "inversa": "artista"}
                }
            },
            "opera": {
                "relazioni": {
                    "artista": {"target": "artista", "inversa": "opere"}
                }
            },
        }
    }
    return rows, config


class RemediatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    def tearDown(self):
        self.temporary.cleanup()

    def write_inputs(self, issues):
        issues_path = self.base / "issues.json"
        dump(issues_path, issues)
        return issues_path

    def make_plan(self, issues, mode="apply"):
        issues_path = self.write_inputs(issues)
        return remediator.build_plan(
            issues,
            self.rules,
            mode=mode,
            issues_path=issues_path,
            rules_path=RULES_PATH,
            generated_at="2026-08-18T00:00:00Z",
        )

    def test_plan_uses_all_four_classifications(self):
        cases = [issue("R03"), issue("S01"), issue("Q01"), issue("N01")]
        plan = self.make_plan(cases, mode="analyze")
        self.assertEqual(
            plan["summary"]["by_classification"],
            {
                "AUTO_FIX": 1,
                "HUMAN_DECISION": 1,
                "RESEARCH_REQUIRED": 1,
                "SCHEMA_CHANGE": 1,
            },
        )
        self.assertEqual(len(plan["actions"]), 4)

    def test_unknown_issue_code_fails_closed(self):
        with self.assertRaisesRegex(remediator.RemediationError, "lassificazione assente"):
            self.make_plan([issue("X99")])

    def test_apply_r03_updates_only_inverse_on_copy(self):
        rows, config = fixture()
        rows_path = self.base / "rows.json"
        config_path = self.base / "config.json"
        dump(rows_path, rows)
        dump(config_path, config)
        original_hash = digest(rows_path)
        plan = self.make_plan([issue()])

        output, log = remediator.apply_plan(
            plan,
            rows,
            config,
            actor="test",
            rows_path=rows_path,
            config_path=config_path,
            generated_at="2026-08-18T00:00:00Z",
        )

        self.assertEqual(output["artista"][0]["relazioni"]["opere"], ["work-1"])
        self.assertEqual(rows["artista"][0]["relazioni"]["opere"], [])
        self.assertEqual(digest(rows_path), original_hash)
        self.assertEqual(log["summary"]["applied"], 1)
        self.assertEqual(log["operations"][0]["before"], [])
        self.assertEqual(log["operations"][0]["after"], ["work-1"])

    def test_r03_is_removed_by_existing_validator(self):
        rows, config = fixture()
        rows_path = self.base / "rows.json"
        config_path = self.base / "config.json"
        before_path = self.base / "before.json"
        after_path = self.base / "after.json"
        dump(rows_path, rows)
        dump(config_path, config)
        dump(before_path, rows)
        before = validator.r_relazioni(validator.carica_rows(before_path), config)
        self.assertEqual([entry.codice for entry in before], ["R03"])

        plan = self.make_plan([issue()])
        output, _ = remediator.apply_plan(
            plan,
            rows,
            config,
            actor="test",
            rows_path=rows_path,
            config_path=config_path,
        )
        dump(after_path, output)
        after = validator.r_relazioni(validator.carica_rows(after_path), config)
        self.assertNotIn("R03", [entry.codice for entry in after])

    def test_non_auto_issue_never_changes_rows(self):
        rows, config = fixture()
        rows_path = self.base / "rows.json"
        config_path = self.base / "config.json"
        dump(rows_path, rows)
        dump(config_path, config)
        plan = self.make_plan([issue("Q01")])

        output, log = remediator.apply_plan(
            plan,
            rows,
            config,
            actor="test",
            rows_path=rows_path,
            config_path=config_path,
        )

        self.assertEqual(output, rows)
        self.assertEqual(log["operations"], [])
        self.assertEqual(log["summary"]["non_applicative_issues"], 1)

    def test_r03_message_mismatch_fails_without_mutating_input(self):
        rows, config = fixture()
        original = copy.deepcopy(rows)
        rows_path = self.base / "rows.json"
        config_path = self.base / "config.json"
        dump(rows_path, rows)
        dump(config_path, config)
        plan = self.make_plan([issue(message="Messaggio non riconducibile al grafo")])

        with self.assertRaisesRegex(remediator.RemediationError, "non deterministica"):
            remediator.apply_plan(
                plan,
                rows,
                config,
                actor="test",
                rows_path=rows_path,
                config_path=config_path,
            )
        self.assertEqual(rows, original)

    def test_cli_refuses_to_overwrite_rows_input(self):
        rows, config = fixture()
        rows_path = self.base / "rows.json"
        config_path = self.base / "config.json"
        issues_path = self.write_inputs([issue()])
        dump(rows_path, rows)
        dump(config_path, config)
        result = remediator.main(
            [
                "apply",
                "--issues",
                str(issues_path),
                "--rules",
                str(RULES_PATH),
                "--plan",
                str(self.base / "plan.json"),
                "--rows",
                str(rows_path),
                "--config",
                str(config_path),
                "--out-rows",
                str(rows_path),
                "--log",
                str(self.base / "log.json"),
            ]
        )
        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
