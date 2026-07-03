#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import json, os

home = Path.home()
core = home / ".gmv_core"
dropbox = home / "Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM"

targets = [
    home / ".gmv_scripts",
    home / ".gmv_runtime",
    home / "Library/LaunchAgents",
    dropbox / "99_SYSTEM",
    dropbox / "90_DAILY_LOGS",
    dropbox / "94_MORNING_BRIEF",
    dropbox / "97_CALIBUR",
    dropbox / "88_PROJECT_PANEL",
    dropbox / "09_DEALS",
]

extensions = {".py", ".sh", ".plist", ".md", ".txt", ".json", ".env"}

items = []
for base in targets:
    if not base.exists():
        continue
    for p in base.rglob("*"):
        if p.is_file() and (p.suffix in extensions or p.name.startswith("com.gmv")):
            try:
                stat = p.stat()
                items.append({
                    "path": str(p),
                    "name": p.name,
                    "suffix": p.suffix,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
                })
            except Exception as e:
                items.append({"path": str(p), "error": str(e)})

out = {
    "inventory": "GMV Legacy Inventory",
    "created_at": datetime.now().isoformat(timespec="seconds"),
    "count": len(items),
    "items": sorted(items, key=lambda x: x.get("modified", ""), reverse=True)
}

out_dir = core / "05_OUTPUT/legacy_inventory"
out_dir.mkdir(parents=True, exist_ok=True)

json_path = out_dir / f"{datetime.now().strftime('%Y_%m_%d_%H%M%S')}_LEGACY_INVENTORY.json"
md_path = out_dir / f"{datetime.now().strftime('%Y_%m_%d_%H%M%S')}_LEGACY_INVENTORY.md"

json_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))

lines = [
    "# GMV LEGACY INVENTORY",
    "",
    f"Created at: {out['created_at']}",
    f"Files found: {out['count']}",
    "",
    "## Items",
    ""
]

for item in out["items"]:
    lines.append(f"- `{item.get('path')}`")
    lines.append(f"  - modified: {item.get('modified', 'n/a')}")
    lines.append(f"  - size: {item.get('size', 'n/a')}")
    lines.append("")

md_path.write_text("\n".join(lines))

print("=== LEGACY INVENTORY CREATED ===")
print("Files found:", out["count"])
print("JSON:", json_path)
print("MD:", md_path)
