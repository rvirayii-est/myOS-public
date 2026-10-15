# myOS architecture

## Components and where each fact lives (One Home Per Fact)
| Fact | Home | Read by | Written by |
| --- | --- | --- | --- |
| Code, commits, branches, worktrees | product git repo | `myos status/resume/verify` (read-only, `--no-optional-locks`, never fetch) | you and your agents |
| Issues, PRs, releases | GitHub | `gh ... -R <card.github>` when asked | you |
| Project routing (repo path, hub, aliases) | card frontmatter `projects/<id>.md` | `myos route` | you (edit card) |
| Operational summary, next action, blockers | card `handoff` block | status, resume, brief | `myos save` |
| Live evidence snapshot | card `live` block | status, brief | `myos verify`, `myos save` |
| Decisions, narratives, session history | Obsidian vault | `myos search/resume` | you, `myos save` (sessions only) |
| Computed relationships | `data/graph/<corpus>/graphify-out/graph.json` | `myos search/resume`, `myos graph query` | `myos graph build/update` |
| Active agent sessions, worktrees | Orca | Orca UI / `orca` CLI | Orca |

Cards point to evidence, they do not copy it. Unknown = `UNVERIFIED`.

## ICM adaptation
ICM (Interpretable Context Methodology) loads context in layers and stops early.
| Layer | myOS file | Budget |
| --- | --- | --- |
| 0 orientation | `CLAUDE.md` / `AGENTS.md`, plus the small global block in `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` | ~40-60 lines |
| 1 routing | `CONTEXT.md` + `myos route` | <80 lines |
| 2 contract | `projects/<id>.md`, `engagements/<id>/ENGAGEMENT.md`, `workflows/<name>.md` | <100 lines each |
| 3 references | `schemas/`, `config/exclusion-policy.json` | as needed |
| 4 working artifacts | vault notes, live git, graph edges | a handful, chosen by search/resume |

ICM principles kept: one home per fact, one-way references (cards -> vault, never the reverse except one link
to the card in hub notes myOS creates), plain-text interfaces, every output is an editable Markdown file, and
"configure the factory": cards and workflows are set up once and reused per session. The ICM *stage pipeline*
(numbered stage folders) was not copied, because myOS routes between projects rather than running a
content-production pipeline.

## Final retrieval pipeline (v1.0)
```
request
  -> 1 project identity   myos route: cwd -> git common dir -> card; worktrees map to their main repo; shared repos
                          narrow by subfolder; ambiguous -> agent asks (or lists candidates and stops if it cannot ask)
  -> 2 ICM status card    projects/<id>.md: claim + source, LIVE block, handoff, open decisions (~140 tokens via route)
  -> 3 graph nodes        built_graphs(project, engagement): only corpora of this project/engagement; every edge carries
                          EXTRACTED/INFERRED + score + source_file; missing or corrupt graph -> skipped silently
  -> 4 source evidence    deterministic search over this engagement's vault scope (project folders + vault_related, minus
                          vault_exclude, minus notes naming other engagements); path:line citations; secrets redacted
  -> 5 live git           read-only git --no-optional-locks; never fetch; session_delta = commits since the last record
  -> 6 agent work         guarded by scripts/guard.py (Claude) and myos-guard.rules (Codex)
```
Measured sizes: `resume` ~1,300 tokens, `search` ~500, `status` ~900, compact `brief` ~830. A real ~270-note vault was about
810,000 tokens, so the vault is never loaded wholesale.

## Concurrency and recovery
- Per-card lock (`logs/locks/<id>.lock`, O_EXCL, stale after 120 s). `save` and `verify` re-read the card under the lock.
- Every multi-file write goes through a journal (`logs/journal`): temp file, then `os.replace`. `myos recover` replays interrupted writes.
- Session records are keyed by session id. An identical re-save (same fingerprint) writes nothing.
- Tested: two simultaneous saves (both recorded), concurrent reads (identical output), interrupted-write replay.

## Knowledge-graph consent
A corpus is built only if its approval still matches its scope (include/exclude), its policy (equal or stricter) **and**
its content (per-file SHA-256 recorded at approval). Any added, changed or removed file makes the state `RE-APPROVAL needed`
and the build refuses before staging. Approvals require an interactive terminal (TTY), and the guard denies agent attempts.

## Ponytail (Phase 4)
Ponytail 5.2.0 is a plugin for Claude Code and Codex (both Codex homes). Its default is pinned to `lite` in
`%APPDATA%\ponytail\config.json`, because the plugin's own default would be `full`. It injects its ruleset once at
SessionStart (~770 tokens), and its hooks write only their own mode and state files. It has no PreToolUse hooks, so it does
not interact with the myOS guard. The A/B results are in `ponytail-benchmark.md`.

## Retrieval pipeline (original description)
1. **Identify**: `myos route` maps cwd -> `git rev-parse --git-common-dir` -> main repo -> card.
   This works the same in `C:\projects\x`, an Orca worktree or `.claude/worktrees`. Fallbacks are the Orca
   workspace folder name, then the vault folder. Shared repos narrow by subfolder (`repo_subpaths`).
2. **Card**: pointers, claim + source, latest handoff.
3. **Graph**: `graph_context()` reads `graph.json` from corpora built from the current vault. It prints edges
   with confidence tag, score and source file.
4. **Notes**: deterministic search (term coverage, filename/heading/frontmatter weighting, type filter,
   project scoping, secret redaction in snippets). This is also the fallback when no graph exists.
5. **Repo**: live read-only git.
No database or server. Everything is files plus one stdlib Python script.

## Write path and recovery (`myos save`)
- Input: JSON written by the agent. The CLI adds its own git evidence (branch, HEAD, status, diff stat).
- Tests marked `passed` without evidence become `claimed-passed-NO-EVIDENCE`.
- Idempotency: one session note per project per day. Sections are keyed by session id and replaced on
  re-save. An identical re-save (same fingerprint) writes nothing.
- Crash safety: a journal `logs/journal/*.pending.json` holds the full target content. Files are written
  temp -> `os.replace`, then the journal is marked done. `myos recover` (and every `save`) replays any
  pending journal. Hooks are not relied on: an agent killed mid-session simply has no record, and you can
  run /save-progress from a new session.

## Engagement isolation
Cards carry `engagement`. Graph corpora are explicit folder allow-lists, so no corpus spans engagements
unless you define one. Search can be scoped with `--project`.
