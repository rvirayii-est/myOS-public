# Security and guards

## Permission model (the owner's choice, preserved)
- Orca Agent Permissions: **Yolo**. Claude is launched with `--dangerously-skip-permissions` and Codex with
  `--dangerously-bypass-approvals-and-sandbox`.
- Claude Code global `defaultMode: bypassPermissions`.
- myOS **never** changes these. Safety comes from the guard below, which works inside bypass modes.

## The myOS guard
**Claude Code:** a PreToolUse hook, `scripts/guard.py`, registered in `~\.claude\settings.json` next to Orca's hooks and the
Ponytail plugin's hooks. It runs on Bash, PowerShell, Read, Edit, Write, MultiEdit, NotebookEdit, Grep and Glob.

**Codex:** exec-policy rules `myos-guard.rules` in `~\.codex\rules` and in Orca's Codex home. These rules are `forbidden`,
and they hold even under `--dangerously-bypass-approvals-and-sandbox`.

| Decision | What |
| --- | --- |
| **deny** (always) | force-push and remote branch deletion; `reset --hard`; `clean -f`; `branch -D`; forced worktree removal; `stash clear`; history rewrites; recursive delete of the drive, `C:\projects`, any repo or worktree root, `.git`, the vault or its top folders, `~\.claude`, `~\.codex`, Orca data or myOS; destructive SQL when a database client is in the command; `flyway clean`, `supabase db reset`, `dotnet ef database drop`; running Graphify directly; agents running `myos graph approve`; uploading a secret file; the canary `myos-guard-selftest` |
| **deny, owner can lift per session** | mutating commands (ssh, scp, rsync, psql, POST/PUT/DELETE) against the hosts listed in `config/guard.json` `production_hosts` |
| **ask** (you confirm in the Orca tab; headless runs are blocked) | reading `.env`/keys/credentials; `git add` of secret files; `git restore .`; soft branch or worktree deletion; deploy and infra commands; editing the guard; cross-engagement file access; a `myos` query or search that reaches another engagement (flags, `--cwd`, `cd`); vault-wide or `C:\projects`-wide searches from a project session |
| allow | everything else, including `git push`, builds, tests, cleaning build folders, `cp .env.example .env`, and health-check GETs |

**Production override (session-scoped).** Start the agent from a terminal where you set
`$env:MYOS_GUARD_ALLOW='production-host'`. It lasts only for that process; close the terminal and it is gone. Agents cannot
set it, and the Graphify gate, recursive-delete protection and the canary can never be overridden.

**Disable the guard for one session:** `$env:MYOS_GUARD='off'` before launching. **Remove:** `scripts\uninstall.ps1`.
**Log:** `logs\guard.log` (redacted; one line per decision).

## Verified (final round)
| Check | Evidence |
| --- | --- |
| Destructive git denied | unit tests; live headless bypass runs; Codex full-bypass runs (only against a scratch repo) |
| "ask" prompts in interactive Orca Yolo | the on-screen Yes/No prompt was seen and No was chosen; the synthetic secret value appears 0 times in the transcript |
| Production-host protection | unit tests (deny, owner override, never-exempt rules). **No real production host was contacted.** |
| Cross-engagement boundaries | a leak (an agent `cd`-ing into myOS to query another engagement) was found, fixed and covered by regression tests |
| False positives | quoted text, heredocs and regex patterns are treated as data; delete checks are scoped to their own command segment; allow-list tests of everyday commands |
| PowerShell | `Remove-Item -Recurse`, `Get-Content .env`, `pwsh -Command "…"` and Windows PowerShell 5.1 under its default policy are covered |
| Coexistence with Ponytail | Orca run with Ponytail lite active: canary blocked; Ponytail injects once; guard hook still registered |
| Concurrent Orca sessions | the guard is stateless per call. Other Orca sessions ran alongside all tests, and the guard logged decisions for them independently |

## Data protection
- **Vault:** myOS never commits it, and writes only new notes. The notes myOS created are listed by `myos manifest`;
  existing notes are never rewritten.
- **External transmission:** only through Graphify, only for approved corpora, and **only if the content is unchanged since
  approval**. Any added, changed or removed file requires re-approval, which only you can give, in your own terminal.
  Notes you name in a corpus `exclude` list, and credential-bearing notes, are excluded.
- **Search snippets** are redacted. Retrieval is scoped to the session's engagement.
- **Backups** are local only, secret-scanned, and exclude credential files and staged note copies.

## Known residual risks
- In bypass modes, anything the guard does not cover runs without a prompt (your accepted trade-off).
- Codex rules are prefix-based, so an unusual flag order may slip through. The Claude hook is broader.
- An ask may not prompt in non-Orca hosts (observed once in this setup harness). Production actions are therefore deny, not ask.
- If your vault contains plaintext secrets, rotate them and move them out of notes; exclusion is a safety net, not a vault.
