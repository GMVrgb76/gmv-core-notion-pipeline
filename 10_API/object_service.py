#!/usr/bin/env python3
import importlib
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

CLIInputError = importlib.import_module("gmv_core.errors").CLIInputError
validate_cli_oid = importlib.import_module("gmv_core.validation").validate_cli_oid
objects_repository = importlib.import_module("gmv_core.repositories.objects")
database = importlib.import_module("gmv_core.database")

def list_objects():
    with database.connect() as conn:
        return objects_repository.list_objects(conn)

def count_objects():
    with database.connect() as conn:
        return objects_repository.count_objects(conn)

def show_object(oid):
    oid = validate_cli_oid(oid).value
    with database.connect() as conn:
        return objects_repository.get_object(conn, oid)

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  object_service.py list")
        print("  object_service.py count")
        print("  object_service.py show <OID>")
        sys.exit(2)

    cmd = sys.argv[1]

    if cmd == "list":
        for row in list_objects():
            print("|".join("" if v is None else str(v) for v in row))

    elif cmd == "count":
        for row in count_objects():
            print("|".join(str(v) for v in row))

    elif cmd == "show":
        if len(sys.argv) < 3:
            print("Usage: object_service.py show <OID>")
            sys.exit(2)
        try:
            row = show_object(sys.argv[2])
        except CLIInputError as error:
            print(f"error: {error}", file=sys.stderr)
            sys.exit(error.exit_code)
        if not row:
            print("Object not found")
            sys.exit(1)
        labels = ["OID", "Type", "Name", "Status", "Created", "Updated"]
        for label, value in zip(labels, row):
            print(f"{label}: {value if value is not None else ''}")

    else:
        print("Unknown command:", cmd)
        sys.exit(2)

if __name__ == "__main__":
    main()
