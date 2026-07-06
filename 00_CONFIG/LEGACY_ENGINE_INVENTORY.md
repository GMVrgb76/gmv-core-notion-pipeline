# GMV Legacy Engine Boundary Inventory

Status: Approved Sprint 002 inventory baseline
Task: S002-02
Backlog: `ARC-008` inventory slice
Captured: 2026-07-06

## Scope and authority

This inventory records the current Morning Brief, Daily Log, and Market Engine
boundaries without copying their source, changing LaunchAgents, executing the
Engines, or granting the external files canonical authority. Hashes are the
version evidence until S002-05 establishes controlled local release entrypoints.

## Registered-service resolution

| Service OID | Registry name | Classification | Inventory record |
|---|---|---|---|
| `SRV-000001` | Knowledge Engine | Native Core runtime; not a legacy compatibility target | `~/.gmv_core/01_RUNTIME/knowledge_engine.py` |
| `SRV-000002` | Morning Brief | Legacy compatibility service | `LEG-MORNING-BRIEF-001` |
| `SRV-000003` | Daily Log | Legacy compatibility service | `LEG-DAILY-LOG-001` |
| `SRV-000004` | Market Engine | Legacy compatibility service | `LEG-MARKET-ENGINE-001` |

All four registered services resolve to a native entrypoint or a versioned
legacy inventory record. Registry status alone does not prove that an Engine is
scheduled or currently executing.

## LEG-MORNING-BRIEF-001

- **Service:** `SRV-000002` — Morning Brief.
- **Source:** `~/.gmv_scripts/genera_morning_brief.sh`.
- **Declared version:** unavailable; the source declares no semantic version.
- **Frozen version:** SHA-256
  `da605bab0a3aaaadcb8077174792a054aae5ff60529bd27ab557ad24d627e1e8`.
- **Observed source metadata:** 9,896 bytes; modified
  `2026-06-26T14:27:08+0200`.
- **Core compatibility entrypoint:**
  `~/.gmv_core/12_SCHEDULER/run_morning_brief_compatibility.sh`, SHA-256
  `516d4475b9d9be9d5e1c5c67953f3c10df8be8091fb8e0df01eb66f2cae56064`.
- **Execution environment:** LaunchAgent `com.gmv.morningbrief` invokes
  `/bin/bash -lc` on the compatibility entrypoint; scheduled at 07:00 and loaded
  at the Sprint baseline. The legacy script invokes `/opt/homebrew/bin/python3`,
  macOS `date`, `rsync`, and local SMTP at `127.0.0.1:1025`.
- **Reads:** selected Markdown/text state under
  `~/Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM/`, plus local runtime mirrors
  under `~/.gmv_runtime/`.
- **Writes:** Dropbox `94_MORNING_BRIEF/`, local runtime mirror directories,
  Core compatibility stdout/stderr artifacts, `engine_runs`, and `timeline`; it
  also sends email through the local SMTP endpoint.
- **Ownership:** no accountable owner is recorded in the service registry,
  LaunchAgent, wrapper, or source. Operational ownership is therefore
  **UNAVAILABLE** pending explicit assignment.
- **Security finding:** the inspected source contains embedded authentication
  material. This inventory intentionally does not reproduce it. Remediation
  belongs to `SEC-004`/`ROAD-006`; the source remains unchanged here.

## LEG-DAILY-LOG-001

- **Service:** `SRV-000003` — Daily Log.
- **Source:** `~/.gmv_scripts/genera_daily_log.sh`.
- **Declared version:** unavailable; the source declares no semantic version.
- **Frozen version:** SHA-256
  `e1ef8e5f7aa51f61d20871e82ebf4f968073d65791e03743373421bae64c8e09`.
- **Observed source metadata:** 1,207 bytes; modified
  `2026-06-23T10:58:18+0200`.
- **Core compatibility entrypoint:**
  `~/.gmv_core/12_SCHEDULER/run_daily_log_compatibility.sh`, SHA-256
  `2e10a67a4c414d5f4163da6ecb278d82d8ff3ae7b86cb1fce7efc72694fae52b`.
- **Execution environment:** LaunchAgent `com.gmv.dailylog` invokes
  `/bin/bash -lc` on the compatibility entrypoint; scheduled at 06:30 and loaded
  at the Sprint baseline. The legacy script uses macOS/BSD shell utilities.
- **Reads:** Markdown and text files beneath the Dropbox GMV Master System,
  filtered by modification time and excluded output paths.
- **Writes:** Dropbox `90_DAILY_LOGS/`, Core compatibility stdout/stderr
  artifacts, `engine_runs`, and `timeline`.
- **Ownership:** no accountable owner is recorded in the available registry,
  LaunchAgent, wrapper, or source. Operational ownership is **UNAVAILABLE**
  pending explicit assignment.

## LEG-MARKET-ENGINE-001

- **Service:** `SRV-000004` — Market Engine.
- **Source:**
  `~/Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM/99_SYSTEM/02_SERVICES/RealEstate/market_engine.py`.
- **Declared version:** source output declares `DOCUMENTAL V2`; this is a domain
  output label, not a release contract.
- **Frozen version:** SHA-256
  `e8309aaa15deb6595d903b6ae9e6748d33a2ce9ddae71d3f628648435f4ac15b`.
- **Observed source metadata:** 5,012 bytes; modified
  `2026-06-28T19:54:20+0200`.
- **Core compatibility entrypoint:**
  `~/.gmv_core/12_SCHEDULER/run_market_engine_compatibility.sh`, SHA-256
  `1d8b68e72e7476753131ccf73d1d6614208f282d352370f8cf80409581cca08b`.
- **Execution environment:** the wrapper passes a Python command string to the
  compatibility layer. No `com.gmv.market*` LaunchAgent was installed or loaded
  at the Sprint baseline.
- **Reads:** Dropbox Markdown below `02_IMMOBILI/00_MARKET/` and
  `02_IMMOBILI/02_COMPARABLES/`.
- **Writes:** Dropbox `MARKET_REPORT.md` and `MARKET_STATUS.md` when executed,
  plus Core compatibility stdout/stderr artifacts, `engine_runs`, and `timeline`.
- **Ownership:** no accountable owner is recorded in the available registry,
  wrapper, or source. Operational ownership is **UNAVAILABLE** pending explicit
  assignment.

## Shared compatibility boundary

The three wrappers call `~/.gmv_core/10_API/gmv_compatibility.py`, frozen for this
inventory at SHA-256
`56367c6e1390e3cc368e00443b50df97e9c349f035ba0bb7d764f30ab9572395`.
It currently owns compatibility output files and records `engine_runs` and
`timeline` rows. Its command-string and `shell=True` behavior is not approved;
S002-03 must replace it with validated argument vectors without changing the
legacy sources or LaunchAgents.

## Boundary decisions

1. External source remains evidence, not Core source.
2. Hash mismatch invalidates the inventory version and blocks execution through
   the future pinned entrypoint until reviewed.
3. Ownership gaps remain explicit and are not filled by inference.
4. Dropbox and LaunchAgents are read-only for this inventory task.
5. S002-03 owns command safety; S002-04 owns process bounds; S002-05 owns pinned
   reproducible local entrypoints.
