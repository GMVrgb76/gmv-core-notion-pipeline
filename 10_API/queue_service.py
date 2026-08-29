#!/usr/bin/env python3
import importlib
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

CLIInputError = importlib.import_module("gmv_core.errors").CLIInputError
validate_positive_id = importlib.import_module("gmv_core.validation").validate_positive_id
queue_repository = importlib.import_module("gmv_core.repositories.queue")
database = importlib.import_module("gmv_core.database")


def list_queue(pending_only=False):
    with database.connect() as conn:
        return queue_repository.list_queue(conn, pending_only=pending_only)


def show_queue_entry(import_id):
    import_id = validate_positive_id(import_id, argument="import_id")
    with database.connect() as conn:
        return queue_repository.get_queue_entry(conn, import_id)


def print_row(row):
    print("|".join("" if value is None else str(value) for value in row))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  queue_service.py list")
        print("  queue_service.py pending")
        print("  queue_service.py show <import_id>")
        sys.exit(2)

    command = sys.argv[1]
    if command == "list":
        for row in list_queue():
            print_row(row)
    elif command == "pending":
        for row in list_queue(pending_only=True):
            print_row(row)
    elif command == "show":
        if len(sys.argv) < 3:
            print("Usage: queue_service.py show <import_id>")
            sys.exit(2)
        try:
            row = show_queue_entry(sys.argv[2])
        except CLIInputError as error:
            print(f"error: {error}", file=sys.stderr)
            sys.exit(error.exit_code)
        if not row:
            print("Queue entry not found")
            sys.exit(1)
        labels = [
            "Import ID", "Resource OID", "Filename", "Status", "Review Status",
            "Proposed Destination", "Confidence", "Error", "Created", "Updated",
        ]
        for label, value in zip(labels, row):
            print(f"{label}: {value if value is not None else ''}")
    else:
        print("Unknown command:", command)
        sys.exit(2)


if __name__ == "__main__":
    main()
