#!/usr/bin/env python3
import importlib
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

search_repository = importlib.import_module("gmv_core.repositories.search")
database = importlib.import_module("gmv_core.database")


def search(query):
    with database.connect() as conn:
        return search_repository.search(conn, query)


def main():
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print("Usage: search_service.py <query>")
        sys.exit(2)

    for row in search(query):
        print("|".join("" if value is None else str(value) for value in row))


if __name__ == "__main__":
    main()
