# AGENTS.md: grokhack-index

Instructions for AI coding agents (Grok, Cursor, Claude Code, Codex, Copilot and others) working **in** this repo or **using it as a building block**. Humans: see [README.md](README.md).

## What this is

Nightly index of the Grok/xAI integration surface (endpoints, models, features, env vars, SDK exports, packages, code snippets with commit-pinned URLs) across the forks listed in awesome-grokhack, with a static search UI and an inverted index.

- Kind: index, dataset, cli · stability: `beta` · licence: MIT
- Machine-readable manifest: [`blocks.json`](blocks.json) (schema: [BLOCKS-SCHEMA](https://github.com/Blockchains/.github/blob/main/docs/BLOCKS-SCHEMA.md))
- How it fits with the other Blockchains repos: [Build with Blocks](https://github.com/Blockchains/.github/blob/main/docs/BUILD-WITH-BLOCKS.md)

## Setup

```bash
python3 --version   # stdlib only
```

## Build and test

```bash
python3 indexer/check.py data
python3 indexer/grokindex.py --repos /tmp/two.json --out /tmp/out --jobs 2 && python3 indexer/check.py /tmp/out   # small end-to-end run
```

## Structure

| Path | What |
|---|---|
| `indexer/grokindex.py` | shallow-clone + scan + write shards/parts/stats |
| `indexer/search.py` | CLI search |
| `indexer/check.py` | consistency checks |
| `indexer/site_data.py` | copies data for docs/ |
| `data/` | published index |
| `docs/` | static search page |
| `repos.json` | last run's repo list |

## Conventions

- A file counts only if it contains an anchor (api.x.ai, XAI_API_KEY, xai-sdk, @ai-sdk/xai, grok-<version> …).
- Snippets keep their project's licence, shown per part.
- Clones are deleted right after scanning.

## Extension points

- New feature detector: add a pattern in `indexer/grokindex.py` and a check in `indexer/check.py`.

## Do

- Let the nightly job regenerate `data/`.

## Don't

- Hand-edit `data/` or `docs/data/`.
- Invent data, mock network responses in shipped code, or hard-code values that should come from the live source; every repo here is 'no mocks, real data'.
- Commit secrets, keys or `.env` files. Run `gitleaks` before pushing; CI and the org policy reject leaks.

## Using it from another project

- **data/parts.json** (http): `composable parts: repo-surface, sdk-exports, code-snippet, package`
- **data/repos/<owner>__<repo>.json** (file): `one shard per fork`
- **indexer/search.py** (cli): `python3 indexer/search.py "streaming tool calling typescript" --data data`
- **search UI** (web): `https://blockchains.github.io/grokhack-index/`

See the README section [Use as a building block](README.md#use-as-a-building-block) for a copy-paste example.

## Related blocks

- [Blockchains/awesome-grokhack](https://github.com/Blockchains/awesome-grokhack): source repo list
- [Blockchains/grokhack-forge](https://github.com/Blockchains/grokhack-forge): consumes parts to compose apps
- [Blockchains/grok-tools-chat](https://github.com/Blockchains/grok-tools-chat): parts recorded in its PARTS.md
