"""Transaction-bound Object identity allocation."""

from __future__ import annotations

import sqlite3

from gmv_core.errors import OIDAllocationError
from gmv_core.identity import TYPE_TO_PREFIX, validate_oid

MAX_OID_SEQUENCE = 999999


def allocate_and_create_object(
    connection: sqlite3.Connection,
    *,
    object_type: str,
    name: str,
    status: str,
    created_at: str,
    updated_at: str,
) -> str:
    """Create an Object and transaction-local OID candidate atomically."""
    if not connection.in_transaction:
        raise OIDAllocationError("OID allocation requires an active transaction")

    prefix = TYPE_TO_PREFIX.get(object_type)
    if prefix is None:
        raise OIDAllocationError(f"unsupported Object type: {object_type}")

    row = connection.execute(
        """
        UPDATE oid_sequences
        SET last_value = last_value + 1
        WHERE object_type = ? AND prefix = ? AND last_value < ?
        RETURNING last_value
        """,
        (object_type, prefix, MAX_OID_SEQUENCE),
    ).fetchone()
    if row is None:
        sequence = connection.execute(
            "SELECT last_value FROM oid_sequences WHERE object_type=? AND prefix=?",
            (object_type, prefix),
        ).fetchone()
        if sequence is None:
            raise OIDAllocationError(
                f"OID sequence is not initialized for Object type: {object_type}"
            )
        raise OIDAllocationError(f"OID sequence exhausted for Object type: {object_type}")

    candidate = f"{prefix}-{int(row[0]):06d}"
    validate_oid(candidate, expected_type=object_type)
    connection.execute(
        """
        INSERT INTO objects (oid,type,name,status,created_at,updated_at)
        VALUES (?,?,?,?,?,?)
        """,
        (candidate, object_type, name, status, created_at, updated_at),
    )
    return candidate
