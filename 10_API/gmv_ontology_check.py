#!/usr/bin/env python3
"""Minimal predicate/entity governance check against a JSON ontology registry
(00_CONFIG/GMV_ONTOLOGY_REGISTRY_REALESTATE_v0.1.json's shape: entity_classes[]
with class_id, predicates[] with predicate_id/domain[]/range[]).

Deliberately small and standalone -- not a port of gmv_atom_validator.py, which
lives on the unmerged worktree-bridge-cse_01EFSz2nNresRvPh9GbfwwzK branch and
depends on that branch's 18-field ATOM schema and Epistemic Ingestion Rules,
neither of which exist on main. This module only checks the two invariants
gmv_property_claims.py actually needs: is a predicate registered at all, and
does a given subject entity class fall within its declared domain.
"""
from __future__ import annotations

import json
from pathlib import Path


class UngovernedPredicateError(RuntimeError):
    def __init__(self, predicate_id: str):
        super().__init__(f"predicate not governed by registry: {predicate_id}")
        self.predicate_id = predicate_id


class DomainMismatchError(RuntimeError):
    def __init__(self, predicate_id: str, subject_type: str, allowed: list[str]):
        super().__init__(f"{predicate_id}: subject type {subject_type!r} not in declared domain {allowed}")
        self.predicate_id = predicate_id
        self.subject_type = subject_type
        self.allowed = allowed


def load_registry(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _predicate(predicate_id: str, registry: dict) -> dict | None:
    for pred in registry.get("predicates", []):
        if pred["predicate_id"] == predicate_id:
            return pred
    return None


def predicate_is_governed(predicate_id: str, registry: dict) -> bool:
    return _predicate(predicate_id, registry) is not None


def subject_type_matches_domain(subject_type: str, predicate_id: str, registry: dict) -> bool:
    """True only if predicate_id is governed AND subject_type is in its domain[].
    A predicate not in the registry at all is a domain mismatch too (nothing to
    match against), not a separate error path a caller could accidentally skip."""
    pred = _predicate(predicate_id, registry)
    if pred is None:
        return False
    return subject_type in pred.get("domain", [])


def object_matches_range(predicate_id: str, value, registry: dict) -> bool:
    """True if predicate_id is governed AND value is plausibly compatible with its
    declared range[] type. Only checks range: ["integer"]/["number"] -- both require
    at least one digit somewhere in value, deliberately loose (matches an
    already-accepted style where the object embeds surrounding label text
    alongside the real value, e.g. '(a) TOTALE MAGGIOR TRIBUTO (IMPOSTA) 1.276,00'
    for ha_maggior_tributo, a real live example already validated). This catches a
    real live bug found 2026-09-29: ha_anno_imposta (range: ["integer"]) holding
    'TARI' or 'TASSA SMALTIMENTO RIFIUTI (TARI)' -- a tax-type label with zero
    digits, not a year -- without rejecting anything previously accepted.

    range: ["date"] is deliberately NOT checked here -- same reasoning as
    mentions_deadline's own range:[string] choice: a real deadline is sometimes
    only expressible as relative text ("entro sessanta giorni dalla notifica"),
    and rejecting that would lose real information. Entity-class ranges
    (PROPERTY, SOGGETTO, ...) and range:["string"] accept any non-empty value --
    an entity name or free text can't be validated without a real Notion lookup."""
    pred = _predicate(predicate_id, registry)
    if pred is None:
        return False
    declared = pred.get("range", [])
    if "integer" in declared or "number" in declared:
        return any(ch.isdigit() for ch in str(value))
    return True


def validate_claim(subject_type: str, predicate_id: str, registry: dict) -> None:
    """Raises UngovernedPredicateError / DomainMismatchError; returns None on success.
    Fail-closed by design, matching gmv_evidence_pipeline's own CLAIM_WITHOUT_EVIDENCE
    guard -- an ungoverned or mistyped claim must never silently pass through."""
    pred = _predicate(predicate_id, registry)
    if pred is None:
        raise UngovernedPredicateError(predicate_id)
    domain = pred.get("domain", [])
    if subject_type not in domain:
        raise DomainMismatchError(predicate_id, subject_type, domain)
