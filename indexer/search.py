#!/usr/bin/env python3
"""Query the search index: search.py "streaming tool calling python" [--data data] [--type code-snippet] [-n 15]"""
import argparse, json, re
ap = argparse.ArgumentParser(); ap.add_argument("q"); ap.add_argument("--data", default="data"); ap.add_argument("--type"); ap.add_argument("-n", type=int, default=15)
a = ap.parse_args()
parts = json.load(open(f"{a.data}/parts.json")); idx = json.load(open(f"{a.data}/search-index.json"))["index"]
syn = {"tool": "tool_calling", "tools": "tool_calling", "calling": "tool_calling", "search": "live_search", "structured": "structured_output", "json": "structured_output", "image": "image_generation"}
terms = []
for t in re.findall(r"[a-z0-9][a-z0-9.\-]+", a.q.lower()):
    terms.append(t)
    if t in syn: terms.append(syn[t])
scores = {}
for t in terms:
    for k in ([t] + ([t.replace("_", "-")] if "_" in t else [])):
        for i in idx.get(k, []): scores[i] = scores.get(i, 0) + 1
ranked = sorted(scores, key=lambda i: (scores[i], parts[i].get("stars") or 0), reverse=True)
if a.type: ranked = [i for i in ranked if parts[i]["type"] == a.type]
for i in ranked[: a.n]:
    p = parts[i]
    print(f"{scores[i]:2} {p['type']:13} {p['id'][:90]:90} {p.get('license')} {p.get('stars')}")
