#!/usr/bin/env python3
import importlib
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

services_repository = importlib.import_module("gmv_core.repositories.services")
database = importlib.import_module("gmv_core.database")


def list_services():
    with database.connect() as conn:
        return services_repository.list_services(conn)


def list_runs():
    with database.connect() as conn:
        return services_repository.list_runs(conn)


def show_service(service_oid):
    with database.connect() as conn:
        return services_repository.get_service(conn, service_oid)


def print_row(row):
    print("|".join("" if value is None else str(value) for value in row))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  service_service.py list")
        print("  service_service.py runs")
        print("  service_service.py show <SRV-OID>")
        sys.exit(2)

    command = sys.argv[1]
    if command == "list":
        for row in list_services():
            print_row(row)
    elif command == "runs":
        for row in list_runs():
            print_row(row)
    elif command == "show":
        if len(sys.argv) < 3:
            print("Usage: service_service.py show <SRV-OID>")
            sys.exit(2)
        row = show_service(sys.argv[2])
        if not row:
            print("Service not found")
            sys.exit(1)
        labels = ["OID", "Name", "Status", "Created", "Updated"]
        for label, value in zip(labels, row):
            print(f"{label}: {value if value is not None else ''}")
    else:
        print("Unknown command:", command)
        sys.exit(2)


if __name__ == "__main__":
    main()
