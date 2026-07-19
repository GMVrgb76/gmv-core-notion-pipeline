#!/usr/bin/env python3

import importlib
import sqlite3
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

database_module = importlib.import_module("gmv_core.database")

DB = Path.home() / ".gmv_core/09_DATABASE/GMV.db"

class BaseService:

    def __init__(self):
        self.conn = database_module.connect_path(DB)
        self.conn.row_factory = sqlite3.Row

    def query(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()

    def one(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur.fetchone()

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        self.conn.commit()

    def print_rows(self, rows):
        if rows is None:
            print("No result")
            return

        if not rows:
            print("Empty")
            return

        for row in rows:
            if isinstance(row, sqlite3.Row):
                print("|".join("" if v is None else str(v) for v in row))
            else:
                print("|".join("" if v is None else str(v) for v in row))

    def close(self):
        self.conn.close()
