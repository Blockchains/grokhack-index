#!/usr/bin/env python3
"""grokhack-index: index the Grok/xAI integration surface of a set of git repos.

Usage: grokindex.py --repos repos.json --out data [--work /tmp/gi-work] [--jobs 6] [--only owner/name,...]
repos.json: list of {"fork": "Blockchains/x", "upstream": "owner/x", "category": ..., "stars": N, "license": SPDX, ...}
For each repo: shallow clone (depth 1, LFS off) of the fork, scan text files, write data/repos/<owner>__<name>.json,
delete the clone. Then build data/parts.json (composable integration parts), data/search-index.json (inverted index)
and data/stats.json. Stdlib only. Everything is extracted from real file contents; nothing is inferred from names alone."""
import argparse, collections, concurrent.futures as cf, datetime, json, os, re, shutil, subprocess, sys, time

TEXT_EXT = {".py",".ts",".tsx",".js",".mjs",".cjs",".jsx",".go",".rs",".java",".kt",".rb",".php",".cs",".swift",".dart",".ex",".exs",
            ".scala",".lua",".sh",".toml",".yaml",".yml",".json",".md",".mdx",".env",".example",".ini",".cfg",".txt",".vue",".svelte",".zig",".c",".cpp",".h"}
SKIP_DIR = re.compile(r"(^|/)(node_modules|vendor|dist|build|out|target|\.git|\.next|coverage|site-packages|__pycache__|\.venv|venv|bower_components|third_party)(/|$)")
MAXFILE = 600_000
# A file is part of the Grok/xAI surface only if it matches one of these anchors.
ANCHOR = re.compile(r"api\.x\.ai|XAI_API_KEY|GROK_API_KEY|xai[-_]sdk|@ai-sdk/xai|langchain[-_]xai|ChatXAI|createXai|\bxai\.(?:Client|AsyncClient)|\bgrok-(?:\d|beta|vision|code|imagine)", re.I)
RE_ENDPOINT = re.compile(r"(?:https?://api\.x\.ai)?(/v1/(?:chat/completions|completions|responses|messages|embeddings|models|language-models|image-generation-models|images/generations|images/edits|tokenize-text|api-key|files|batches|documents/search|realtime|audio/speech|audio/transcriptions|videos(?:/generations)?|collections|deferred-completion|embedding-models))\b")
RE_HOST = re.compile(r"\b(api\.x\.ai|management-api\.x\.ai|us-east-1\.api\.x\.ai|eu-west-1\.api\.x\.ai)\b")
RE_MODEL = re.compile(r"\bgrok-(?:\d[\w.\-]*|beta|vision-beta|code[\w.\-]*|imagine[\w.\-]*)\b")
RE_ENV = re.compile(r"\b([A-Z][A-Z0-9_]*(?:XAI|GROK)[A-Z0-9_]*|XAI_[A-Z0-9_]+)\b")
FEATURES = {
    "tool_calling": re.compile(r"\btool_choice\b|\btool_calls\b|\btools\s*[:=]\s*[\[{]|function_call|toolCall|tool_use|parallel_tool_calls"),
    "streaming": re.compile(r"\bstream\s*[:=]\s*(?:true|True)\b|text/event-stream|streamText|\.stream\(|stream_options|for await|AsyncStream|SSE\b"),
    "structured_output": re.compile(r"response_format|json_schema|generateObject|structured[_ ]output|\.parse\(|with_structured_output"),
    "live_search": re.compile(r"search_parameters|web_search|x_search|live[_ ]search|SearchParameters|searchParameters"),
    "vision": re.compile(r"image_url|input_image|grok-\d[\w.\-]*vision|grok-vision"),
    "image_generation": re.compile(r"images/generations|grok-\d[\w.\-]*image|grok-imagine|generateImage|image_generation"),
    "reasoning": re.compile(r"reasoning_effort|reasoning_content|reasoningEffort|grok-\d[\w.\-]*(?:mini|reasoning)"),
    "embeddings": re.compile(r"/v1/embeddings|embedding"),
    "voice_realtime": re.compile(r"/v1/realtime|realtime|audio/speech|voice"),
    "mcp": re.compile(r"\bMCP\b|modelcontextprotocol|mcp[-_]server|@modelcontextprotocol"),
    "grpc": re.compile(r"grpc|\.proto\b|protobuf"),
    "openai_compatible": re.compile(r"base_?url\s*[:=]\s*[\"']https://api\.x\.ai/v1|baseURL\s*:\s*[\"']https://api\.x\.ai/v1|OpenAI\(|openai\.OpenAI|createOpenAI"),
    "anthropic_compatible": re.compile(r"/v1/messages|anthropic"),
}
LANG = {".py":"Python",".ts":"TypeScript",".tsx":"TypeScript",".js":"JavaScript",".mjs":"JavaScript",".cjs":"JavaScript",".jsx":"JavaScript",".go":"Go",".rs":"Rust",
        ".java":"Java",".kt":"Kotlin",".rb":"Ruby",".php":"PHP",".cs":"C#",".swift":"Swift",".dart":"Dart",".ex":"Elixir",".exs":"Elixir",".scala":"Scala",".lua":"Lua",".vue":"Vue",".svelte":"Svelte",".zig":"Zig"}
CODE_EXT = set(LANG)
RE_TS_EXPORT = re.compile(r"^export\s+(?:declare\s+)?(?:async\s+)?(?:function\*?|const|let|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)|^export\s*\{([^}]*)\}", re.M)
RE_PY_ALL = re.compile(r"__all__\s*=\s*[\[(]([^\])]*)[\])]", re.S)
RE_PY_DEF = re.compile(r"^(?:class|def|async def)\s+([A-Za-z_]\w*)", re.M)
LIC_FILE = re.compile(r"^(LICEN[CS]E|COPYING)(\.md|\.txt)?$", re.I)

def sh(cmd, cwd=None, timeout=900):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"})

def kind_of(path):
    p = path.lower()
    if re.search(r"(^|/)(tests?|__tests__|spec|e2e|fixtures?)(/|$)|_test\.|\.test\.|\.spec\.", p): return "test"
    if re.search(r"(^|/)(examples?|cookbook|demos?|samples?|notebooks?)(/|$)", p): return "example"
    if p.endswith((".md", ".mdx", ".txt")) or "/docs/" in "/" + p: return "doc"
    if p.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env", ".example")): return "config"
    return "source"

def snippet(lines, idx, before=6, after=18):
    a, b = max(0, idx - before), min(len(lines), idx + after)
    return a + 1, b, "\n".join(l[:200] for l in lines[a:b])

def scan_repo(rec, work):
    fork = rec["fork"]; slug = fork.replace("/", "__")
    d = os.path.join(work, slug)
    shutil.rmtree(d, ignore_errors=True)
    t0 = time.time()
    url = f"https://github.com/{fork}.git"
    tok = os.environ.get("GH_CLONE_TOKEN")
    if tok: url = f"https://x-access-token:{tok}@github.com/{fork}.git"
    p = sh(["git", "clone", "--depth", "1", "--single-branch", "--no-tags", "-q", url, d], timeout=1500)
    if p.returncode != 0:
        return {"fork": fork, "upstream": rec.get("upstream"), "status": "clone-failed", "error": p.stderr.decode()[-300:]}
    head = sh(["git", "rev-parse", "HEAD"], cwd=d).stdout.decode().strip()
    du = sh(["du", "-sk", d]).stdout.decode().split()[0]
    files_total = 0; lang = collections.Counter(); hits = []
    endpoints = collections.Counter(); hosts = collections.Counter(); models = collections.Counter(); env = collections.Counter()
    feats = collections.Counter(); exports = []; packages = []; licence_text = None; snippets = []
    for root, dirs, files in os.walk(d):
        rel_root = os.path.relpath(root, d)
        dirs[:] = [x for x in dirs if not SKIP_DIR.search((rel_root + "/" + x).lstrip("./"))]
        for fn in files:
            path = os.path.normpath(os.path.join(rel_root, fn)); full = os.path.join(root, fn)
            ext = os.path.splitext(fn)[1].lower()
            if rel_root == "." and LIC_FILE.match(fn) and licence_text is None:
                try: licence_text = " ".join(open(full, errors="replace").read(1500).split())[:400]
                except Exception: pass
            if ext not in TEXT_EXT and fn not in ("Dockerfile", ".env.example"): continue
            files_total += 1
            if ext in CODE_EXT: lang[LANG[ext]] += 1
            try:
                if os.path.getsize(full) > MAXFILE: continue
                txt = open(full, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            if not ANCHOR.search(txt): continue
            k = kind_of(path)
            lines = txt.splitlines()
            f_end = sorted(set(m.group(1) for m in RE_ENDPOINT.finditer(txt)))
            f_mod = sorted(set(RE_MODEL.findall(txt)))
            f_env = sorted(set(e for e in RE_ENV.findall(txt) if len(e) <= 40))
            f_host = sorted(set(RE_HOST.findall(txt)))
            f_feat = sorted(n for n, rx in FEATURES.items() if rx.search(txt))
            for x in f_end: endpoints[x] += 1
            for x in f_mod: models[x] += 1
            for x in f_env: env[x] += 1
            for x in f_host: hosts[x] += 1
            if k in ("source", "example"):
                for x in f_feat: feats[x] += 1
            h = {"path": path, "kind": k, "lang": LANG.get(ext), "lines": len(lines), "endpoints": f_end, "models": f_mod[:40], "env": f_env, "features": f_feat}
            # SDK / provider exports (only for source files inside an xai/grok-named path)
            if k == "source" and re.search(r"(^|/|[-_])(xai|grok)([-_/.]|$)", path.lower()):
                if ext in (".ts", ".tsx", ".js", ".mjs") and re.search(r"(^|/)index\.[mc]?[tj]sx?$", path):
                    names = []
                    for m in RE_TS_EXPORT.finditer(txt):
                        if m.group(1): names.append(m.group(1))
                        else: names += [x.strip().split(" as ")[-1].strip() for x in m.group(2).split(",") if x.strip()]
                    if names: exports.append({"path": path, "lang": "TypeScript", "names": sorted(set(n for n in names if n))[:80]})
                elif ext == ".py" and fn == "__init__.py":
                    m = RE_PY_ALL.search(txt)
                    names = re.findall(r"[\"'](\w+)[\"']", m.group(1)) if m else []
                    if names: exports.append({"path": path, "lang": "Python", "names": sorted(set(names))[:80]})
                elif ext == ".py":
                    names = [n for n in RE_PY_DEF.findall(txt) if not n.startswith("_")]
                    if names and len(exports) < 60: exports.append({"path": path, "lang": "Python", "names": names[:40]})
            if fn == "package.json" and (re.search(r"(xai|grok)", path.lower()) or "/" not in path):
                try:
                    pj = json.loads(txt); packages.append({"path": path, "ecosystem": "npm", "name": pj.get("name"), "version": pj.get("version")})
                except Exception: pass
            if fn == "pyproject.toml" and (re.search(r"(xai|grok)", path.lower()) or "/" not in path):
                m = re.search(r'^name\s*=\s*"([^"]+)"', txt, re.M); v = re.search(r'^version\s*=\s*"([^"]+)"', txt, re.M)
                if m: packages.append({"path": path, "ecosystem": "pypi", "name": m.group(1), "version": v.group(1) if v else None})
            # one snippet per source/example code file, at the first strong anchor
            if k in ("source", "example") and ext in CODE_EXT and len(snippets) < 40:
                for i, l in enumerate(lines):
                    if re.search(r"api\.x\.ai|XAI_API_KEY|@ai-sdk/xai|xai_sdk|ChatXAI|createXai|xai\.Client", l):
                        a, b, s = snippet(lines, i); snippets.append({"path": path, "start": a, "end": b, "code": s}); break
            hits.append(h)
    shutil.rmtree(d, ignore_errors=True)
    kinds = collections.Counter(h["kind"] for h in hits)
    return {
        "fork": fork, "upstream": rec.get("upstream"), "category": rec.get("category"), "stars": rec.get("stars"),
        "license_spdx": rec.get("license"), "license_text_head": licence_text, "pushed_at": rec.get("pushed_at"),
        "description": rec.get("description"), "commit": head, "indexed_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ok", "clone_kb": int(du), "seconds": round(time.time() - t0, 1),
        "files_scanned": files_total, "languages": dict(lang.most_common(8)),
        "grok_files": len(hits), "grok_files_by_kind": dict(kinds),
        "hosts": dict(hosts.most_common()), "endpoints": dict(endpoints.most_common()), "models": dict(models.most_common(60)),
        "env_vars": dict(env.most_common(30)), "features": dict(feats.most_common()),
        "sdk_exports": exports[:60], "packages": packages[:20], "snippets": snippets, "files": hits[:400],
    }

TOK = re.compile(r"[a-z0-9][a-z0-9.\-]{1,40}")
def tokens(*parts):
    out = set()
    for p in parts:
        if not p: continue
        for t in TOK.findall(str(p).lower()):
            out.add(t.strip(".-"))
    return {t for t in out if len(t) > 1}

def build_parts(shards):
    parts = []
    for s in shards:
        if s.get("status") != "ok" or not s["grok_files"]: continue
        base = {"repo": s["fork"], "upstream": s["upstream"], "license": s["license_spdx"], "stars": s["stars"], "category": s["category"], "commit": s["commit"]}
        caps = sorted(s["features"]); models = list(s["models"])[:20]; env = list(s["env_vars"])[:10]; eps = list(s["endpoints"])
        parts.append({**base, "id": f"{s['fork']}#repo", "type": "repo-surface", "languages": list(s["languages"])[:4],
                      "capabilities": caps, "models": models, "endpoints": eps, "env_vars": env,
                      "grok_files": s["grok_files"], "description": s["description"]})
        for e in s["sdk_exports"][:12]:
            parts.append({**base, "id": f"{s['fork']}#{e['path']}", "type": "sdk-exports", "path": e["path"], "lang": e["lang"], "exports": e["names"][:40]})
        for sn in s["snippets"][:10]:
            f = next((h for h in s["files"] if h["path"] == sn["path"]), {})
            parts.append({**base, "id": f"{s['fork']}#{sn['path']}:{sn['start']}", "type": "code-snippet", "path": sn["path"], "lang": f.get("lang"),
                          "start": sn["start"], "end": sn["end"], "capabilities": f.get("features", []), "models": f.get("models", [])[:10],
                          "endpoints": f.get("endpoints", []), "env_vars": f.get("env", []),
                          "url": f"https://github.com/{s['fork']}/blob/{s['commit']}/{sn['path']}#L{sn['start']}-L{sn['end']}"})
        for p in s["packages"]:
            parts.append({**base, "id": f"{s['fork']}#pkg:{p['name']}", "type": "package", **p})
    return parts

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--work", default="/tmp/gi-work"); ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--only", default=""); ap.add_argument("--rebuild-only", action="store_true")
    a = ap.parse_args()
    repos = json.load(open(a.repos))
    if a.only: repos = [r for r in repos if r["fork"] in a.only.split(",")]
    os.makedirs(f"{a.out}/repos", exist_ok=True); os.makedirs(a.work, exist_ok=True)
    t0 = time.time()
    if not a.rebuild_only:
        with cf.ThreadPoolExecutor(a.jobs) as ex:
            futs = {ex.submit(scan_repo, r, a.work): r for r in repos}
            for fu in cf.as_completed(futs):
                r = futs[fu]
                try: s = fu.result()
                except Exception as e: s = {"fork": r["fork"], "upstream": r.get("upstream"), "status": "error", "error": str(e)[:300]}
                json.dump(s, open(f"{a.out}/repos/{r['fork'].replace('/', '__')}.json", "w"), indent=1)
                print(f"{s['status']:12} {r['fork']:55} grok_files={s.get('grok_files')} {s.get('seconds')}s", flush=True)
    wanted = {r["fork"] for r in json.load(open(a.repos))}
    shards = []
    for fn in sorted(os.listdir(f"{a.out}/repos")):
        s = json.load(open(f"{a.out}/repos/{fn}"))
        if s["fork"] in wanted: shards.append(s)
        else: os.remove(f"{a.out}/repos/{fn}")
    parts = build_parts(shards)
    json.dump(parts, open(f"{a.out}/parts.json", "w"), indent=0)
    inv = collections.defaultdict(set)
    for i, p in enumerate(parts):
        for t in tokens(p["id"], p.get("description"), p.get("category"), " ".join(p.get("capabilities", [])), " ".join(p.get("models", [])),
                        " ".join(p.get("endpoints", [])), " ".join(p.get("env_vars", [])), " ".join(p.get("exports", [])[:40]), p.get("lang"), " ".join(p.get("languages", [])), p.get("name")):
            inv[t].add(i)
    json.dump({"version": 1, "parts": len(parts), "index": {k: sorted(v) for k, v in sorted(inv.items())}}, open(f"{a.out}/search-index.json", "w"), separators=(",", ":"))
    ok = [s for s in shards if s.get("status") == "ok"]
    agg = lambda key: dict(sum((collections.Counter({k: 1 for k in s.get(key, {})}) for s in ok), collections.Counter()).most_common(40))
    stats = {"generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "repos_listed": len(wanted),
             "repos_indexed_ok": len(ok), "repos_failed": [s["fork"] for s in shards if s.get("status") != "ok"],
             "repos_with_grok_surface": sum(1 for s in ok if s["grok_files"]), "grok_files": sum(s["grok_files"] for s in ok),
             "files_scanned": sum(s["files_scanned"] for s in ok), "clone_mb_total": round(sum(s["clone_kb"] for s in ok) / 1024, 1),
             "parts": len(parts), "parts_by_type": dict(collections.Counter(p["type"] for p in parts)), "search_tokens": len(inv),
             "repos_per_endpoint": agg("endpoints"), "repos_per_model": agg("models"), "repos_per_feature": agg("features"), "repos_per_env_var": agg("env_vars"),
             "run_seconds": round(time.time() - t0, 1)}
    json.dump(stats, open(f"{a.out}/stats.json", "w"), indent=1)
    print(json.dumps({k: stats[k] for k in ("repos_indexed_ok", "repos_with_grok_surface", "grok_files", "parts", "search_tokens", "run_seconds")}))
    if not ok: sys.exit(1)

if __name__ == "__main__": main()
