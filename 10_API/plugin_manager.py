#!/usr/bin/env python3
import sqlite3, sys
from pathlib import Path

DB = Path.home() / ".gmv_core/09_DATABASE/GMV.db"

def q(sql, params=()):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows

cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

if cmd == "list":
    for r in q("SELECT plugin_oid, plugin_name, slug, version, status FROM plugin_registry_view ORDER BY plugin_oid"):
        print("|".join(str(x) for x in r))

elif cmd == "services":
    for r in q("SELECT plugin_name, service_oid, service_name, role FROM plugin_services_view WHERE service_oid IS NOT NULL ORDER BY plugin_name"):
        print("|".join(str(x) for x in r))

elif cmd == "info" and len(sys.argv) > 2:
    slug = sys.argv[2]
    rows = q("SELECT plugin_oid, plugin_name, slug, version, status, description FROM plugin_registry_view WHERE slug=?", (slug,))
    if not rows:
        print("Plugin not found")
        sys.exit(1)
    for r in rows:
        print("plugin_oid:", r[0])
        print("name:", r[1])
        print("slug:", r[2])
        print("version:", r[3])
        print("status:", r[4])
        print("description:", r[5])
else:
    print("Usage:")
    print("  plugin_manager.py list")
    print("  plugin_manager.py services")
    print("  plugin_manager.py info <slug>")
    sys.exit(2)
