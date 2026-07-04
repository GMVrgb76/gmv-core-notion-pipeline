# GMV OID Contract

Version: 1.0.0

Status: Accepted

Owner: GMV Core Identity API

Related backlog items: `ARC-004`, `DB-008`

## Purpose

This document is the canonical contract for GMV Object identifiers. It defines only mappings already established by persisted typed Objects. The wider Object type vocabulary does not receive speculative prefixes.

## Grammar

An OID is exactly three uppercase ASCII letters, one hyphen, and six decimal digits:

```text
AAA-000001
```

The numeric sequence is in the inclusive range `000001` through `999999`. Sequence `000000` is invalid.

Whitespace, lowercase letters, accented letters, alternate separators, and digit counts other than six are invalid. Validation is exact and performs no trimming, case conversion, padding, or other normalization.

## Prefix and Type Authority

| Prefix | Object type |
|---|---|
| `COR` | Core |
| `PER` | Person |
| `PLG` | Plugin |
| `RES` | Resource |
| `SRV` | Service |
| `SYS` | System |

An OID is valid for an Object only when its prefix maps to that Object's exact type. Types without a mapping in this table cannot receive an OID under contract version 1.0.0.

## Identity Rules

1. An OID is permanent and immutable.
2. An OID identifies exactly one Object.
3. An allocated OID is never reused, including after rollback, archival, or gaps.
4. Persisted OIDs are never silently normalized or rewritten.
5. Unknown prefixes and unsupported Object types fail validation.
6. Prefix additions or grammar changes require a versioned contract update and compatibility review.

## Implementation Authority

`gmv_core.identity` owns executable validation for this contract. Persistence and CLI adapters must call that validator before database or filesystem access once their approved integration tasks are implemented.
