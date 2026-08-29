#!/usr/bin/env python3
import importlib
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

resources_repository = importlib.import_module("gmv_core.repositories.resources")
database = importlib.import_module("gmv_core.database")


def list_resources():
    with database.connect() as conn:
        return resources_repository.list_resources(conn)


def count_resources():
    with database.connect() as conn:
        return resources_repository.count_resources(conn)


def show_resource(resource_oid):
    with database.connect() as conn:
        return resources_repository.get_resource(conn, resource_oid)


def print_row(row):
    print("|".join("" if value is None else str(value) for value in row))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  resource_service.py list")
        print("  resource_service.py show <RES-OID>")
        print("  resource_service.py count")
        sys.exit(2)

    command = sys.argv[1]
    if command == "list":
        for row in list_resources():
            print_row(row)
    elif command == "show":
        if len(sys.argv) < 3:
            print("Usage: resource_service.py show <RES-OID>")
            sys.exit(2)
        row = show_resource(sys.argv[2])
        if not row:
            print("Resource not found")
            sys.exit(1)
        labels = [
            "OID", "Name", "Object Status", "Path", "Filename", "Extension",
            "Size", "SHA256", "Imported", "Resource Status",
        ]
        for label, value in zip(labels, row):
            print(f"{label}: {value if value is not None else ''}")
    elif command == "count":
        for row in count_resources():
            print_row(row)
    else:
        print("Unknown command:", command)
        sys.exit(2)


if __name__ == "__main__":
    main()
