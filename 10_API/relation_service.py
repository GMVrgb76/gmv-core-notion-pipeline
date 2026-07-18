#!/usr/bin/env python3
import importlib
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

relations_repository = importlib.import_module("gmv_core.repositories.relations")
database = importlib.import_module("gmv_core.database")

def list_relations():
    with database.connect() as conn:
        return relations_repository.list_relations(conn)

def count_relations():
    with database.connect() as conn:
        return relations_repository.count_relations(conn)

def show_relations(oid):
    with database.connect() as conn:
        return relations_repository.get_relations(conn, oid)

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  relation_service.py list")
        print("  relation_service.py count")
        print("  relation_service.py show <OID>")
        sys.exit(2)

    cmd = sys.argv[1]

    if cmd == "list":
        for r in list_relations():
            print("|".join("" if v is None else str(v) for v in r))

    elif cmd == "count":
        for r in count_relations():
            print("|".join(str(v) for v in r))

    elif cmd == "show":
        if len(sys.argv) < 3:
            print("Usage: relation_service.py show <OID>")
            sys.exit(2)
        rows = show_relations(sys.argv[2])
        if not rows:
            print("No relations found")
            sys.exit(1)
        for r in rows:
            print("|".join("" if v is None else str(v) for v in r))

    else:
        print("Unknown command:", cmd)
        sys.exit(2)

if __name__ == "__main__":
    main()
