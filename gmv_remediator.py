#!/usr/bin/env python3
"""GMV Remediator v0.1: plan and apply deterministic local remediations.

The component is deliberately offline.  It reads validator artifacts, writes a
plan, and can create a remediated copy of rows.json.  It has no Notion client
and never mutates the input snapshot.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path


COMPONENT = "GMV Remediator"
VERSION = "0.1"
PLAN_SCHEMA_VERSION = "1.0"
LOG_SCHEMA_VERSION = "1.0"
ACTION_CLASSES = {
    "AUTO_FIX",
    "RESEARCH_REQUIRED",
    "HUMAN_DECISION",
    "SCHEMA_CHANGE",
}
R03_OPERATION = "ADD_MISSING_INVERSE_RELATION"
REQUIRED_ISSUE_FIELDS = {
    "codice",
    "severita",
    "entita",
    "record_id",
    "titolo",
    "campo",
    "messaggio",
    "azione",
}


class RemediationError(RuntimeError):
    """Raised when an artifact or an AUTO_FIX precondition is unsafe."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RemediationError(f"Artefatto JSON non leggibile: {path}: {exc}") from exc


def atomic_json_write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def norm(value) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [item for item in parsed if item not in (None, "")]
        return [item.strip() for item in stripped.split(",") if item.strip()]
    return [value]


def validate_issues(issues) -> None:
    if not isinstance(issues, list):
        raise RemediationError("issues.json deve contenere una lista JSON.")
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            raise RemediationError(f"Issue {index}: atteso un oggetto JSON.")
        missing = REQUIRED_ISSUE_FIELDS - issue.keys()
        if missing:
            raise RemediationError(
                f"Issue {index}: campi obbligatori assenti: {', '.join(sorted(missing))}."
            )
        if any(not isinstance(issue[field], str) for field in REQUIRED_ISSUE_FIELDS):
            raise RemediationError(f"Issue {index}: tutti i campi devono essere stringhe.")


def validate_rules(policy) -> dict:
    if not isinstance(policy, dict) or not isinstance(policy.get("rules"), dict):
        raise RemediationError("remediation_rules.json deve contenere l'oggetto 'rules'.")
    rules = policy["rules"]
    for code, rule in rules.items():
        if not isinstance(rule, dict):
            raise RemediationError(f"Regola {code}: atteso un oggetto JSON.")
        classification = rule.get("classification")
        if classification not in ACTION_CLASSES:
            raise RemediationError(f"Regola {code}: classificazione non valida: {classification!r}.")
        operation = rule.get("operation")
        if classification == "AUTO_FIX" and code != "R03":
            raise RemediationError(
                f"Regola {code}: v0.1 consente AUTO_FIX esclusivamente per R03."
            )
        if classification == "AUTO_FIX" and operation != R03_OPERATION:
            raise RemediationError(
                f"Regola {code}: operazione AUTO_FIX non supportata: {operation!r}."
            )
        if classification != "AUTO_FIX" and operation is not None:
            raise RemediationError(
                f"Regola {code}: le classi non applicative devono avere operation null."
            )
    return rules


def fingerprint(issue: dict, occurrence: int) -> str:
    canonical = json.dumps(issue, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{canonical}\n{occurrence}".encode("utf-8")).hexdigest()
    return f"act-{digest[:20]}"


def build_plan(
    issues: list,
    policy: dict,
    *,
    mode: str,
    issues_path: Path,
    rules_path: Path,
    generated_at: str | None = None,
) -> dict:
    validate_issues(issues)
    rules = validate_rules(policy)
    missing_rules = sorted({issue["codice"] for issue in issues} - rules.keys())
    if missing_rules:
        raise RemediationError(
            "Classificazione assente in remediation_rules.json per: " + ", ".join(missing_rules)
        )

    seen = Counter()
    actions = []
    by_class = Counter()
    for issue in issues:
        canonical = json.dumps(issue, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        seen[canonical] += 1
        rule = rules[issue["codice"]]
        classification = rule["classification"]
        by_class[classification] += 1
        actions.append(
            {
                "action_id": fingerprint(issue, seen[canonical]),
                "classification": classification,
                "authorization_required": rule["authorization_required"],
                "risk": rule["risk"],
                "rule": {
                    "issue_code": issue["codice"],
                    "operation": rule.get("operation"),
                    "reason": rule["reason"],
                },
                "proposed_action": rule["proposed_action"],
                "issue": copy.deepcopy(issue),
            }
        )

    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "component": COMPONENT,
        "component_version": VERSION,
        "mode": mode,
        "generated_at": generated_at or utc_now(),
        "sources": {
            "issues": {"path": str(issues_path), "sha256": sha256_file(issues_path)},
            "rules": {"path": str(rules_path), "sha256": sha256_file(rules_path)},
        },
        "summary": {
            "issues": len(issues),
            "by_classification": {name: by_class.get(name, 0) for name in sorted(ACTION_CLASSES)},
            "auto_fix_candidates": by_class.get("AUTO_FIX", 0),
        },
        "actions": actions,
    }


def validate_rows(rows, cfg) -> None:
    if not isinstance(rows, dict):
        raise RemediationError("rows.json deve contenere un oggetto per entità.")
    entities = cfg.get("entita") if isinstance(cfg, dict) else None
    if not isinstance(entities, dict):
        raise RemediationError("config.json deve contenere l'oggetto 'entita'.")
    for entity, records in rows.items():
        if not isinstance(records, list):
            raise RemediationError(f"rows.json: '{entity}' deve contenere una lista.")
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise RemediationError(f"rows.json: {entity}[{index}] non è un oggetto.")
            if not isinstance(record.get("relazioni", {}), dict):
                raise RemediationError(f"rows.json: {entity}[{index}].relazioni non è un oggetto.")


def build_indexes(rows: dict):
    by_id = {}
    by_title = {}
    for entity, records in rows.items():
        for record in records:
            record_id = record.get("id")
            if record_id:
                key = str(record_id)
                if key in by_id:
                    raise RemediationError(f"ID duplicato in rows.json: {key}")
                by_id[key] = (entity, record)
            title_key = (entity, norm(record.get("titolo")))
            by_title.setdefault(title_key, []).append(record)
    return by_id, by_title


def resolve_record(reference, target_entity: str, by_id: dict, by_title: dict):
    exact = by_id.get(str(reference))
    if exact and exact[0] == target_entity:
        return exact[1]
    candidates = by_title.get((target_entity, norm(reference)), [])
    return candidates[0] if len(candidates) == 1 else None


def relation_contains(values, record: dict) -> bool:
    record_id = str(record.get("id", ""))
    title = norm(record.get("titolo"))
    return any(str(value) == record_id or norm(value) == title for value in as_list(values))


def apply_r03(action: dict, rows: dict, cfg: dict, indexes: tuple) -> dict:
    issue = action["issue"]
    by_id, by_title = indexes
    located = by_id.get(issue["record_id"])
    if not located or located[0] != issue["entita"]:
        raise RemediationError(
            f"{action['action_id']}: record sorgente non risolto: "
            f"{issue['entita']} {issue['record_id']}"
        )
    source_entity, source = located
    source_spec = cfg["entita"].get(source_entity, {})
    relation_spec = source_spec.get("relazioni", {}).get(issue["campo"])
    if not relation_spec:
        raise RemediationError(
            f"{action['action_id']}: relazione non configurata: {source_entity}.{issue['campo']}"
        )
    target_entity = relation_spec.get("target")
    inverse = relation_spec.get("inversa")
    if not target_entity or not inverse:
        raise RemediationError(f"{action['action_id']}: metadati target/inversa incompleti.")

    target_relation = (
        cfg["entita"].get(target_entity, {}).get("relazioni", {}).get(inverse)
    )
    if not target_relation:
        raise RemediationError(
            f"{action['action_id']}: relazione inversa non configurata: {target_entity}.{inverse}"
        )
    if (
        target_relation.get("target") != source_entity
        or target_relation.get("inversa") != issue["campo"]
    ):
        raise RemediationError(
            f"{action['action_id']}: configurazione inversa non bidirezionale."
        )

    matches = []
    for reference in as_list(source.get("relazioni", {}).get(issue["campo"])):
        target = resolve_record(reference, target_entity, by_id, by_title)
        if target is None:
            continue
        expected_message = (
            f"Relazione asimmetrica: '{target.get('titolo', '')}' non riporta "
            f"'{source.get('titolo', '')}' in '{inverse}'."
        )
        if expected_message == issue["messaggio"]:
            matches.append(target)
    if len(matches) != 1:
        raise RemediationError(
            f"{action['action_id']}: destinazione R03 non deterministica "
            f"(corrispondenze: {len(matches)})."
        )

    target = matches[0]
    relations = target.setdefault("relazioni", {})
    before = copy.deepcopy(relations.get(inverse, []))
    if relation_contains(before, source):
        return {
            "result": "SKIPPED_ALREADY_RESOLVED",
            "target": {
                "entita": target_entity,
                "record_id": target.get("id", ""),
                "titolo": target.get("titolo", ""),
                "field_path": f"relazioni.{inverse}",
            },
            "before": before,
            "after": copy.deepcopy(before),
        }

    if not isinstance(before, list):
        raise RemediationError(
            f"{action['action_id']}: la relazione inversa non è una lista JSON."
        )
    after = before + [source["id"]]
    relations[inverse] = after
    return {
        "result": "APPLIED",
        "target": {
            "entita": target_entity,
            "record_id": target.get("id", ""),
            "titolo": target.get("titolo", ""),
            "field_path": f"relazioni.{inverse}",
        },
        "before": before,
        "after": copy.deepcopy(after),
    }


def apply_plan(
    plan: dict,
    rows: dict,
    cfg: dict,
    *,
    actor: str,
    rows_path: Path,
    config_path: Path,
    generated_at: str | None = None,
) -> tuple[dict, dict]:
    validate_rows(rows, cfg)
    remediated = copy.deepcopy(rows)
    indexes = build_indexes(remediated)
    operations = []
    applied_at = generated_at or utc_now()

    for action in plan["actions"]:
        if action["classification"] != "AUTO_FIX":
            continue
        operation = action["rule"]["operation"]
        if operation != R03_OPERATION:
            raise RemediationError(
                f"{action['action_id']}: operazione non supportata: {operation!r}."
            )
        result = apply_r03(action, remediated, cfg, indexes)
        operations.append(
            {
                "action_id": action["action_id"],
                "issue_code": action["issue"]["codice"],
                "operation": operation,
                "reason": action["rule"]["reason"],
                "actor": actor,
                "timestamp": applied_at,
                **result,
            }
        )

    result_counts = Counter(entry["result"] for entry in operations)
    log = {
        "schema_version": LOG_SCHEMA_VERSION,
        "component": COMPONENT,
        "component_version": VERSION,
        "mode": "apply",
        "generated_at": applied_at,
        "actor": actor,
        "sources": {
            "rows": {"path": str(rows_path), "sha256": sha256_file(rows_path)},
            "config": {"path": str(config_path), "sha256": sha256_file(config_path)},
            "issues": plan["sources"]["issues"],
            "rules": plan["sources"]["rules"],
        },
        "summary": {
            "auto_fix_candidates": plan["summary"]["auto_fix_candidates"],
            "applied": result_counts.get("APPLIED", 0),
            "skipped_already_resolved": result_counts.get("SKIPPED_ALREADY_RESOLVED", 0),
            "non_applicative_issues": plan["summary"]["issues"]
            - plan["summary"]["auto_fix_candidates"],
        },
        "operations": operations,
    }
    return remediated, log


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Classifica issue Area35 e applica solo AUTO_FIX deterministici a una copia locale."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    def common(subparser):
        subparser.add_argument("--issues", required=True, type=Path)
        subparser.add_argument("--rules", default=Path("remediation_rules.json"), type=Path)
        subparser.add_argument("--plan", default=Path("plan.json"), type=Path)

    analyze = subparsers.add_parser("analyze", help="Produce solo plan.json.")
    common(analyze)

    apply = subparsers.add_parser(
        "apply", help="Produce piano, copia locale remediata e log operativo."
    )
    common(apply)
    apply.add_argument("--rows", required=True, type=Path)
    apply.add_argument("--config", required=True, type=Path)
    apply.add_argument("--out-rows", default=Path("rows.remediated.json"), type=Path)
    apply.add_argument("--log", default=Path("remediation_log.json"), type=Path)
    apply.add_argument("--actor", default=f"{COMPONENT} v{VERSION}")
    return parser.parse_args(argv)


def ensure_safe_paths(args) -> None:
    inputs = {args.issues.resolve(), args.rules.resolve()}
    outputs = [args.plan.resolve()]
    if args.mode == "apply":
        inputs.update({args.rows.resolve(), args.config.resolve()})
        outputs.extend([args.out_rows.resolve(), args.log.resolve()])
    collisions = inputs.intersection(outputs)
    if collisions:
        joined = ", ".join(str(path) for path in sorted(collisions, key=str))
        raise RemediationError(f"Un output coincide con un input protetto: {joined}")
    if len(set(outputs)) != len(outputs):
        raise RemediationError("I percorsi di output devono essere distinti tra loro.")


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        ensure_safe_paths(args)
        issues = load_json(args.issues)
        policy = load_json(args.rules)
        plan = build_plan(
            issues,
            policy,
            mode=args.mode,
            issues_path=args.issues,
            rules_path=args.rules,
        )
        atomic_json_write(args.plan, plan)
        if args.mode == "analyze":
            print(
                f"Piano: {plan['summary']['issues']} issue; "
                f"AUTO_FIX:{plan['summary']['auto_fix_candidates']} -> {args.plan}"
            )
            return 0

        original_hash = sha256_file(args.rows)
        rows = load_json(args.rows)
        cfg = load_json(args.config)
        remediated, log = apply_plan(
            plan,
            rows,
            cfg,
            actor=args.actor,
            rows_path=args.rows,
            config_path=args.config,
        )
        if sha256_file(args.rows) != original_hash:
            raise RemediationError("Invariante violata: rows.json originale è cambiato.")
        atomic_json_write(args.out_rows, remediated)
        log["outputs"] = {
            "remediated_rows": {
                "path": str(args.out_rows),
                "sha256": sha256_file(args.out_rows),
            }
        }
        atomic_json_write(args.log, log)
        print(
            f"Applicazione locale: {log['summary']['applied']} AUTO_FIX applicati; "
            f"input invariato; output {args.out_rows}; log {args.log}"
        )
        return 0
    except RemediationError as exc:
        print(f"[errore] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
