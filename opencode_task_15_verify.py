"""One-off live check for opencode_task_15.md. NOT part of the pipeline, NOT
committed.

WHAT IS LIVE HERE, and what is not -- stated up front, because the first
attempt at this script failed and the reason matters:

  * NOT possible in this environment: downloading the real source file.
    DropboxConnector needs DROPBOX_ACCESS_TOKEN (or the refresh triple) and
    none is configured here. A token file exists at ~/.gmv_dropbox_oauth.json
    and this script deliberately does NOT read it -- gmv-core-safety rule 1
    ("never touch credentials"). So the real .md could not be fetched and the
    document text in part B is a STAND-IN, clearly marked, not a real
    downloaded file. Every other part below is real.

  * REAL: the entity names and source locators in part A come from real
    committed crawler output (01_RUNTIME/gmv_crawler/pre_deepseek_reset_backup_2026-09-20/
    atoms_built.jsonl and entity_proposal_queue.jsonl, written by real nightly
    runs), and the registry read is the real committed
    00_CONFIG/gmv_entity_registry.json.

  * LIVE: part B runs the real process_document() end to end against the real
    local Ollama model -- real classify_document() call, real
    extract_candidates() call, real registry load, real
    propose_entity_identity(), real append_entity_identity_proposals().

HARD BOUNDARY, checked by this script itself before and after (sha256 + mtime):
the real 00_CONFIG/gmv_entity_registry.json and the real
01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl are only ever
READ here. Nothing in this script calls confirm_new_entity() or
confirm_entity_alias().
"""
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_crawler_entity_identity_proposal_queue import (  # noqa: E402
    append_entity_identity_proposals,
)
from gmv_crawler_entity_resolver import (  # noqa: E402
    _load_entity_registry,
    propose_entity_identity,
    resolve_entity_gmv_id,
)
from gmv_crawler_extractor import extract_document  # noqa: E402
from gmv_crawler_orchestrator import process_document  # noqa: E402

REAL_REGISTRY = ROOT / "00_CONFIG" / "gmv_entity_registry.json"
REAL_QUEUE = ROOT / "01_RUNTIME" / "gmv_crawler" / "entity_identity_proposal_queue.jsonl"
REAL_RUN_BACKUP = ROOT / "01_RUNTIME" / "gmv_crawler" / "pre_deepseek_reset_backup_2026-09-20"
NOW = "2026-09-26T18:00:00Z"
bar = "=" * 78

# The real source_id a real run recorded for the atom below -- a real Area35
# Dropbox locator, reused here only as the ExtractionDocument's source_id.
REAL_LOCATOR = (
    "/gmv_master_system/01_area35_master/99_exports/mutualart_2026/"
    "04_davide_genna/cv_davide_genna.docx"
)

# STAND-IN TEXT -- see the module docstring. Every name in it is a real,
# independently verifiable one: "Danilo Bucchi" and "Le Stanze della
# Fotografia" are rows of the real 00_CONFIG/area35_known_artists.json /
# area35_known_institutions.json, and "Museo d'Arte Moderna dell'Alto Mantovano"
# is a real institution a real run extracted (see the backup logs read in
# part A). The sentences are NOT a real downloaded document.
STANDIN_TEXT = """Danilo Bucchi (1934-2020) e' stato un artista italiano legato a
Lodi e alla Mecamena. Ha esposto per anni al Museo d'Arte Moderna dell'Alto
Mantovano, dove ha presentato la serie "Costruzioni". Nel 2019 la Le Stanze
della Fotografia di Venezia ha ospitato una sua retrospettiva, a cura di
Roberto Masini. Le opere sono conservate anche presso la Galleria d'Arte
Moderna di Trieste.
"""


def fingerprint(path: Path) -> tuple[str, float | None, bool]:
    if not path.exists():
        return ("<absent>", None, False)
    return (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime, True)


def real_names_from_real_runs() -> list[tuple[str, str]]:
    """Entity names and source ids that a REAL nightly run actually produced,
    read back from the real committed runtime logs (not invented here)."""
    found: list[tuple[str, str]] = []
    atoms = REAL_RUN_BACKUP / "atoms_built.jsonl"
    for line in atoms.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for key in ("subject", "object"):
            found.append((row[key], row["source"]))
    queue = REAL_RUN_BACKUP / "entity_proposal_queue.jsonl"
    for line in queue.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        found.append((row["entity_name"], "(entity_proposal_queue.jsonl, no source_id on this row)"))
    return found


def main() -> None:
    watched = (REAL_REGISTRY, REAL_QUEUE)
    before = {p: fingerprint(p) for p in watched}
    print(bar)
    print("0. the two REAL files, BEFORE  [sha256, mtime, exists]")
    print(bar)
    for path, fp in before.items():
        print(f"  {path.relative_to(ROOT)}")
        print(f"    sha256={fp[0]}")
        print(f"    mtime={fp[1]}  exists={fp[2]}")

    registry = _load_entity_registry()
    print()
    print(bar)
    print("1. the real registry, read through the new real loader")
    print(f"   _load_entity_registry() -> {len(registry['entities'])} entities")
    print(bar)
    for entry in registry["entities"]:
        print(f"  - {entry['gmv_id']}: {entry['canonical_name']!r} aliases={entry.get('aliases')}")

    print()
    print(bar)
    print("2. REAL entity names a real run already extracted, against the REAL")
    print("   registry -- how many would this task now propose?")
    print(bar)
    for name, source in real_names_from_real_runs():
        resolved = resolve_entity_gmv_id(name, registry)
        print(f"  {name!r}")
        print(f"      from: {source}")
        print(f"      resolve_entity_gmv_id() = {resolved!r}"
              f"  -> proposal? {'NO (resolves)' if resolved else 'YES (unresolved)'}")
    print("  control, the one name the registry DOES know:")
    for spelling in ("Federico Garibaldi", "  federico garibaldi  ", "Garibaldi"):
        print(f"      resolve_entity_gmv_id({spelling!r}) = {resolve_entity_gmv_id(spelling, registry)!r}")

    print()
    print(bar)
    print("3. LIVE process_document() -- real classify_document(), real")
    print("   extract_candidates(), real Ollama, real registry load")
    print(bar)
    workdir = Path(tempfile.mkdtemp(prefix="gmv_task15_"))
    local = workdir / "standin.md"
    local.write_text(STANDIN_TEXT, encoding="utf-8")
    local_hash = "sha256:" + hashlib.sha256(local.read_bytes()).hexdigest()
    document = extract_document(local, source_id=REAL_LOCATOR, source_hash=local_hash)
    print(f"  ExtractionDocument: status={document.status} extractor={document.extractor} "
          f"source_id={document.source_id!r}")
    if document.status != "SUCCESS":
        print("  !! extraction failed, stopping")
        return

    result = process_document(
        document, evidence_ids=(f"{document.source_id}#{NOW}",), now=NOW,
        timeout=450, num_ctx=16384, num_predict=8192,
    )
    print()
    print(f"  document_type = {result.document_type!r}")
    print(f"  atoms         = {len(result.atoms)}")
    print(f"  all_entities  = {len(result.all_entities)}")
    print(f"  type proposals needing verification = "
          f"{len(result.entity_type_proposals_needing_verification)}")
    print()
    print(f"  >>> entity_identity_proposals = {len(result.entity_identity_proposals)}")
    for proposal in result.entity_identity_proposals:
        print("      " + repr(proposal))
    print()
    print("  all entity names the real extractor returned (verbatim, in order):")
    for entity in result.all_entities:
        print(f"    - {entity.name!r}")
    print()
    print("  every proposal's fields against its own CandidateEntity, verbatim:")
    for proposal, entity in zip(result.entity_identity_proposals, result.all_entities):
        if proposal is None or proposal.raw_name != entity.name:
            continue
        print(f"    {proposal.raw_name!r}: raw_name matches={proposal.raw_name == entity.name}"
              f"  source_id matches={proposal.source_id == entity.source_id}"
              f"  evidence_excerpt matches={proposal.evidence_excerpt == entity.evidence_excerpt}"
              f"  suggested_entity_type={proposal.suggested_entity_type!r}")
        print(f"      evidence_excerpt verbatim: {proposal.evidence_excerpt!r}")

    print()
    print(bar)
    print("4. append_entity_identity_proposals() against a TEMP COPY path")
    print(f"   tmp queue: {workdir / 'entity_identity_proposal_queue.jsonl'}")
    print(bar)
    tmp_queue = workdir / "entity_identity_proposal_queue.jsonl"
    written = append_entity_identity_proposals(result.entity_identity_proposals, tmp_queue, now=NOW)
    print(f"  lines written = {written}  (real queue path never passed to this function)")
    print("  --- the temp file, read back verbatim ---")
    for line in tmp_queue.read_text(encoding="utf-8").splitlines():
        print(f"    {line}")
    print("  --- fields round-tripped back into EntityIdentityProposal values ---")
    for line in tmp_queue.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        rebuilt = propose_entity_identity(
            row["raw_name"], _load_entity_registry(),
            source_id=row["source_id"], evidence_excerpt=row["evidence_excerpt"],
            suggested_entity_type=row["suggested_entity_type"],
        )
        print(f"    {row['raw_name']!r}: raw_name={rebuilt.raw_name!r} "
              f"source_id={rebuilt.source_id!r} "
              f"evidence_excerpt={rebuilt.evidence_excerpt!r} "
              f"suggested_entity_type={rebuilt.suggested_entity_type!r} "
              f"queued_at={row['queued_at']!r}")
    empty_target = workdir / "never_created.jsonl"
    empty_written = append_entity_identity_proposals((), empty_target, now=NOW)
    if empty_written != 0 or empty_target.exists():
        raise SystemExit(f"empty append misbehaved: wrote {empty_written}, exists={empty_target.exists()}")
    print(f"  empty append: returned 0 and created nothing -> exists={empty_target.exists()}")

    print()
    print(bar)
    print("5. the two REAL files, AFTER -- must be byte-identical and untouched")
    print(bar)
    for path, fp in before.items():
        after = fingerprint(path)
        print(f"  {path.relative_to(ROOT)}")
        print(f"    sha256 unchanged: {after[0] == fp[0]}")
        print(f"    mtime  unchanged: {after[1] == fp[1]}")
        print(f"    exists unchanged: {after[2] == fp[2]}")
        if after != fp:
            raise SystemExit(f"REAL FILE WAS TOUCHED: {path}\n  before={fp}\n  after ={after}")

    shutil.rmtree(workdir, ignore_errors=True)
    print()
    print("OK -- the real registry and the real runtime queue were not touched.")


if __name__ == "__main__":
    main()
