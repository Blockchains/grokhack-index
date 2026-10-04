# grokhack-index

Nightly index of the **Grok / xAI integration surface** of every open-source project listed in
[Blockchains/awesome-grokhack](https://github.com/Blockchains/awesome-grokhack) (forked into [github.com/Blockchains](https://github.com/Blockchains)).
Search UI: **https://blockchains.github.io/grokhack-index/** · used by [grokhack.com /forge](https://grokhack.com/forge) via [grokhack-forge](https://github.com/Blockchains/grokhack-forge).

## What is extracted (from real file contents, per repo)
A file counts as Grok/xAI surface only if it contains an anchor: `api.x.ai`, `XAI_API_KEY`, `GROK_API_KEY`, `xai-sdk`/`xai_sdk`, `@ai-sdk/xai`,
`langchain-xai`, `ChatXAI`, `createXai`, `xai.Client`, or a `grok-<version>` model id. For those files:

- **API endpoints** (`/v1/chat/completions`, `/v1/responses`, `/v1/messages`, `/v1/images/generations`, `/v1/embeddings`, `/v1/realtime`, ...) and hosts
- **Models** (`grok-4.6`, `grok-4-fast-reasoning`, `grok-imagine-image`, ...)
- **Features**: tool calling, streaming, structured output, live search, vision, image generation, reasoning, embeddings, voice/realtime, MCP, gRPC, OpenAI/Anthropic-compatible usage
- **Auth / config env vars** (`XAI_API_KEY`, `XAI_BASE_URL`, ...)
- **SDK exports** (TS `index.ts` exports and Python `__all__`/public defs inside xai/grok paths), **packages** (npm/pypi names + versions)
- **Code snippets** (first anchor in each source/example file, <= 24 lines, with commit-pinned URL and licence)
- Licence (SPDX from GitHub + the LICENSE file head), languages, file counts, commit SHA

## Files
- `data/repos/<owner>__<repo>.json` — one shard per fork
- `data/parts.json` — composable parts (`repo-surface`, `sdk-exports`, `code-snippet`, `package`)
- `data/search-index.json` — inverted index token -> part positions
- `data/stats.json` — totals and repos-per-endpoint/model/feature/env var
- `repos.json` — the repo list used for the last run (from awesome-grokhack `grok-forge.json`)

## How it runs
`.github/workflows/nightly-index.yml` (02:41 UTC + manual): refresh `repos.json` from awesome-grokhack -> optional upstream sync (needs `FORK_SYNC_TOKEN`)
-> `indexer/grokindex.py` shallow-clones each fork (`--depth 1`, LFS smudge off, 6 in parallel), scans, **deletes each clone right after**
-> gitleaks on `data/` -> commit if changed. Stdlib-only Python.

```bash
python3 indexer/grokindex.py --repos repos.json --out data --jobs 6
python3 indexer/search.py "streaming tool calling typescript" --data data
python3 indexer/check.py data
```

Code snippets remain under their projects' licences (shown on each part); the indexer and this README are MIT.
