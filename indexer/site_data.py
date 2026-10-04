#!/usr/bin/env python3
"""Copy compact data for the static search page (docs/)."""
import json, os, shutil
os.makedirs("docs/data", exist_ok=True)
for f in ("parts.json", "stats.json", "search-index.json"):
    shutil.copy(f"data/{f}", f"docs/data/{f}")
print("site data updated")
