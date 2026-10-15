# Graphify in myOS

## Install (optional)
- Package `graphifyy` (PyPI name per upstream README) in an isolated venv: `graphify\.venv`
  (`python -m venv graphify\.venv` then `graphify\.venv\Scripts\pip install graphifyy`). myOS was built against 0.9.90.
- Interface used: the documented headless CLI (`graphify extract`, `cluster-only`, `query`), called only by `myos graph ...`.
- Backend: `claude-cli` (`config/myos.json`). Semantic extraction runs through your signed-in Claude Code, so note text goes
  to **Anthropic**. Model alias `sonnet`. myOS strips other providers' API keys from the environment so Graphify cannot pick
  another backend.

## Hardened extraction shim
Graphify pipes note text to `claude -p`. If your global Claude setting is `bypassPermissions`, an instruction hidden in a
note could otherwise make the extraction model run tools. `myos` puts `graphify\shim\claude.cmd` first on PATH. It runs
Claude with `--tools "" --strict-mcp-config --disable-slash-commands --permission-mode default`. An injection probe was
tested: the model attempted a tool call, the call could not execute, and no file was created.

## Why the `/graphify` Claude skill is NOT installed globally
`graphify install` copies a skill whose description says "Use for any question about a codebase". As a global skill it
would fire inside product repositories, write `graphify-out/` into them, send their docs for extraction, and
`pip install graphifyy` into your global Python. The CLI provides everything myOS needs. To opt in for one folder, run
`graphify\.venv\Scripts\graphify.exe install --project --platform windows` from that folder.

## Corpora and approval (`config/myos.json` -> graph.corpora)
| Corpus (example config) | Source | Approval |
| --- | --- | --- |
| `synthetic` | `tests/fixtures/synthetic-vault` | not required (fictional) |
| `vault-pilot` | vault `03-PROJECTS/_myOS-Pilot/**`, `07-TEMPLATES/myOS/*` | **required** |
| `lumen-ledger`, `orbit-queue` | one project folder each | **required** |
| `acme-general` | engagement-level notes | **required** |

Guidelines for your own corpora:
- **Strict allow-lists.** Every corpus names exact folders/files; personal folders appear in none.
- **One engagement per corpus.** Graph context is scoped to the session's project and engagement, so corpora must not span clients.
- **Explicit excludes for known-sensitive notes** (e.g. a meeting transcript with passwords), independent of the scanner.
- **Repo docs only by exception.** Product repository code is never a corpus. A corpus with `"kind": "repo-docs"` may stage
  explicitly listed Markdown design docs from a repo, with approval.

Flow:
1. `myos graph plan <corpus>` stages the files locally and writes `data/graph/<corpus>/TRANSMISSION-PREVIEW.md`: every file,
   its size, the destination provider, what was excluded and why, and "review" flags (patterns found; values never shown).
2. **You** run `myos graph approve <corpus>` in your own terminal (or the guided `scripts\review-corpora.ps1`). It refuses
   non-interactive callers, and the guard denies agents.
3. The approval binds to the include/exclude lists, the exclusion-policy hash **and each file's SHA-256**. Any added, changed
   or removed file shows `RE-APPROVAL needed`, and the build refuses before staging anything.
4. `myos graph build <corpus>` / `myos graph update <corpus>` (incremental: only changed files are re-extracted).

## Exclusion policy (`config/exclusion-policy.json`)
Applied before anything is staged. A hit excludes the whole file, and only the rule name is logged.
- Extensions: only `.md`, `.txt`.
- Directories: `.git .obsidian .trash .claude node_modules dist build target bin obj .venv attachments private
  secrets credentials` and similar.
- Names: `.env*`, key/cert/keystore files, `id_rsa*`, names containing credential/secret/password/token/apikey, db/dump/sql files.
- Content: private-key blocks, AWS keys, GitHub tokens, `sk-`/`sk-ant-` keys, Slack and Google keys, JWTs, URLs with embedded
  credentials, password/secret/token assignments, prose passwords ("password is …"), password table cells, `user / pass`
  pairs, bearer tokens, connection-string passwords and SQL `PASSWORD '…'` literals.

## Sample output (synthetic corpus)
- `data/graph/synthetic/graphify-out/graph.json`, `GRAPH_REPORT.md`, `graph.html`, plus `cache/`.
- First build: 5 docs -> 10 nodes, 13 edges (11 EXTRACTED, 2 INFERRED), 3 communities. 2 files excluded by policy
  (`private/credentials-note.md` excluded-dir, `leaky-session.md` content:github-token).
- After one note changed: "1 docs changed; 4 unchanged", "1 re-extracted".
- Graphify sometimes labels a semantic edge EXTRACTED with a score below 1.0, so myOS always prints the tag **and** the score
  with the source file, and treats INFERRED/AMBIGUOUS as hypotheses.

```
  - Lumen Ledger (project hub) --references--> OrbitQueue  [EXTRACTED 1.0]  src: 03-PROJECTS/LumenLedger/00-Overview.md
  - Event sourcing for journal --references--> OrbitQueue  [EXTRACTED 0.95]  src: .../ADR-001 Use event sourcing for journal.md
```
