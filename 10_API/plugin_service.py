#!/usr/bin/env python3
import importlib
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

database_module = importlib.import_module("gmv_core.database")

DB = Path.home() / ".gmv_core/09_DATABASE/GMV.db"


def connect():
    return database_module.connect_path(DB)


def list_plugins():
    with connect() as conn:
        return conn.execute("""
        SELECT plugin_oid,plugin_name,slug,version,status,description
        FROM plugin_registry_view
        ORDER BY plugin_oid
        """).fetchall()


def list_plugin_services():
    with connect() as conn:
        return conn.execute("""
        SELECT plugin_oid,plugin_name,slug,service_oid,service_name,role
        FROM plugin_services_view
        ORDER BY plugin_oid,service_oid
        """).fetchall()


def show_plugin(identifier):
    with connect() as conn:
        return conn.execute("""
        SELECT plugin_oid,plugin_name,slug,version,status,description
        FROM plugin_registry_view
        WHERE plugin_oid=? OR lower(slug)=lower(?)
        """, (identifier, identifier)).fetchone()


def print_row(row):
    print("|".join("" if value is None else str(value) for value in row))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  plugin_service.py list")
        print("  plugin_service.py services")
        print("  plugin_service.py show <PLG-OID or slug>")
        sys.exit(2)

    command = sys.argv[1]
    if command == "list":
        for row in list_plugins():
            print_row(row)
    elif command == "services":
        for row in list_plugin_services():
            print_row(row)
    elif command == "show":
        if len(sys.argv) < 3:
            print("Usage: plugin_service.py show <PLG-OID or slug>")
            sys.exit(2)
        row = show_plugin(sys.argv[2])
        if not row:
            print("Plugin not found")
            sys.exit(1)
        labels = ["OID", "Name", "Slug", "Version", "Status", "Description"]
        for label, value in zip(labels, row):
            print(f"{label}: {value if value is not None else ''}")
    else:
        print("Unknown command:", command)
        sys.exit(2)


if __name__ == "__main__":
    main()
