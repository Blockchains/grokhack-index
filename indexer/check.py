#!/usr/bin/env python3
"""Sanity checks on an index directory: shards parse, parts reference real shards, stats consistent."""
import json, os, sys
d = sys.argv[1]
stats = json.load(open(f"{d}/stats.json")); parts = json.load(open(f"{d}/parts.json")); idx = json.load(open(f"{d}/search-index.json"))
shards = [json.load(open(f"{d}/repos/{f}")) for f in os.listdir(f"{d}/repos")]
ok = [s for s in shards if s.get("status") == "ok"]
assert ok, "no ok shards"
assert stats["repos_indexed_ok"] == len(ok), (stats["repos_indexed_ok"], len(ok))
assert idx["parts"] == len(parts)
forks = {s["fork"] for s in ok}
assert all(p["repo"] in forks for p in parts), "part references unknown repo"
assert all(len(s["commit"]) == 40 for s in ok), "missing commit sha"
assert sum(s["grok_files"] for s in ok) > 0, "no grok files found"
print(f"OK: {len(ok)} shards, {len(parts)} parts, {stats['grok_files']} grok files, {len(idx['index'])} tokens")
