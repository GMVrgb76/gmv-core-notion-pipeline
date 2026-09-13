"""Characterization test for 00_CONFIG/EPISTEMIC_INGESTION_RULES_v0.2.json.

Guards the shape of the config that will drive the GMV Crawler's
VALIDATE EPISTEMICALLY stage: exactly the 15 rules already validated in
v0.1 (RCV_001 gates 0-5) plus the 4 integrations the audit identified as
due in v0.2 -- no more, no fewer, none malformed.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "00_CONFIG" / "EPISTEMIC_INGESTION_RULES_v0.2.json"
)

VALID_SEVERITIES = {"BLOCKING", "DEFECT", "WEAKNESS"}
VALID_FAMILIES = {
    "assertion_strength",
    "temporal_state",
    "ontology_discipline",
    "atomicity",
    "lifecycle",
}


def _load() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_file_is_valid_json_with_expected_top_level_shape() -> None:
    config = _load()
    assert config["version"] == "0.2"
    assert config["supersedes"] == "0.1"
    assert config["authority"] == "REQUIRED"
    assert "rules" in config
    assert "v0_2_integrations" in config


def test_exactly_fifteen_v0_1_rules_and_four_v0_2_integrations() -> None:
    config = _load()
    assert len(config["rules"]) == 15
    assert len(config["v0_2_integrations"]) == 4


def test_rule_ids_are_unique_and_sequential() -> None:
    config = _load()
    all_entries = config["rules"] + config["v0_2_integrations"]
    ids = [entry["rule_id"] for entry in all_entries]
    assert len(ids) == len(set(ids)), "duplicate rule_id found"
    assert ids == [f"EIC-{n:02d}" for n in range(1, 20)]


def test_every_entry_has_required_fields_with_valid_values() -> None:
    config = _load()
    required_fields = {
        "rule_id",
        "statement",
        "family",
        "severity",
        "failure_classification",
        "source_reference",
    }
    for entry in config["rules"] + config["v0_2_integrations"]:
        assert required_fields <= entry.keys(), entry["rule_id"]
        assert entry["severity"] in VALID_SEVERITIES, entry["rule_id"]
        assert entry["family"] in VALID_FAMILIES, entry["rule_id"]
        assert entry["statement"], entry["rule_id"]
        assert entry["source_reference"], entry["rule_id"]


def test_blocking_rules_declare_ingestion_discipline_failure() -> None:
    config = _load()
    for entry in config["rules"] + config["v0_2_integrations"]:
        if entry["severity"] == "BLOCKING":
            assert entry["failure_classification"] == "INGESTION_DISCIPLINE_FAILURE", (
                entry["rule_id"]
            )


def test_rules_one_through_twelve_are_blocking_per_source_failure_classification() -> None:
    """Regression pin for this file's own transcription choice: rules 1-12
    are BLOCKING/INGESTION_DISCIPLINE_FAILURE, 13-15 are DEFECT, following
    the boundary the source Constitution's Failure classification section
    draws. This test verifies internal self-consistency of the JSON as
    written here -- it is not a check against a cached copy of the source
    Notion document, which this repo does not have. If the transcription
    itself is wrong, this test will not catch that."""
    config = _load()
    by_id = {entry["rule_id"]: entry for entry in config["rules"]}
    for n in range(1, 13):
        assert by_id[f"EIC-{n:02d}"]["severity"] == "BLOCKING"
    for n in range(13, 16):
        assert by_id[f"EIC-{n:02d}"]["severity"] == "DEFECT"


def test_all_v0_2_integrations_are_blocking() -> None:
    config = _load()
    for entry in config["v0_2_integrations"]:
        assert entry["severity"] == "BLOCKING", entry["rule_id"]


def test_operational_test_has_seven_questions() -> None:
    config = _load()
    assert len(config["operational_test"]["questions"]) == 7


def test_no_rule_introduced_beyond_the_documented_nineteen() -> None:
    config = _load()
    assert set(config.keys()) >= {
        "version",
        "supersedes",
        "core_rule",
        "rules",
        "v0_2_integrations",
        "failure_classification",
    }
    total = len(config["rules"]) + len(config["v0_2_integrations"])
    assert total == 19, "translation must not silently introduce new rules"
