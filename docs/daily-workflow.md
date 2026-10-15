# myOS daily workflow

Everything here was verified on 2026-10-15 in real Orca sessions with Yolo, Claude bypass
and Ponytail lite.

## 1. Open Orca
Start Orca. Your worktrees and tabs come back as you left them.

## 2. Select a project
In the left sidebar, pick the repository and worktree you want, e.g. **lumen-ledger -> feature-x**, or create a new worktree.
Then open an agent tab: **Claude** (default) or **Codex**. myOS works out the project from the folder, so you never type its history.

## 3. Resume work
Type **`/resume-project`** (Codex: **`$resume-project`**). The agent reports:
- **LIVE (checked now):** branch, commit, uncommitted files, how far behind `main`, other worktrees.
- **HISTORICAL:** the last saved session (dated), next actions, blockers, open decisions.
- **Stale or conflicting records:** e.g. "the card's next actions are 36 days old" or "3 commits since the last session".

If a folder holds several products, say which one:
- in a monorepo shared by several cards: `/resume-project <card-id>`

Without a name, the agent lists the candidates and stops.

## 4. Search history
**`/context-search <what you want>`**, e.g. `/context-search event sourcing decision` or `/context-search idempotency bug`.
Answers cite `file:line`. Graph links marked INFERRED are suggestions, not facts. Searches stay inside the current engagement;
an Acme tab never shows Globex notes.

## 5. Save progress
At the end of a session: **`/save-progress`** (Codex: `$save-progress`). This writes a dated session note into the vault and
updates the project card's handoff: what changed, tests that actually ran (with output), decisions, blockers and next actions.
Running it twice is safe, and two agents saving at once is safe.

## 6. Switch between Claude and Codex
Save in one (`/save-progress`), then open the other in the same worktree and resume (`$resume-project`). Verified in both
directions: the same session id, test result and next actions come back. Codex works in any terminal too: just type `codex`.

## 7. Ponytail ("write less code"), currently ON at lite
| Do this | How |
| --- | --- |
| Change level for this session | `/ponytail lite`, `/ponytail full`, `/ponytail ultra`, `/ponytail off` (Codex: `$ponytail:ponytail`) |
| Change the default | edit `%APPDATA%\ponytail\config.json`: `{"defaultMode": "lite"}` (or `off`) |
| Turn it off for one launch | `$env:PONYTAIL_DEFAULT_MODE='off'`, then start the agent from that terminal |
| Disable / re-enable entirely | `claude plugin disable ponytail@ponytail` / `claude plugin enable ponytail@ponytail` |
| Review a diff | `/ponytail-review` |

Codex: Ponytail's skills are available now. To have it auto-activate in Codex, open `codex`, type `/hooks`, and trust the
two Ponytail hooks (one time). Measured effect of lite: `docs/ponytail-benchmark.md`.

## 8. Update approved knowledge graphs
- Status: `python C:\projects\myOS\scripts\myos.py graph list`
- Review and approve, in your own PowerShell window:
  `powershell -ExecutionPolicy Bypass -File C:\projects\myOS\scripts\review-corpora.ps1`
- After **any** change to an approved corpus (e.g. a new session note), re-approval is required before an update. The list
  shows `RE-APPROVAL needed` and names the changed files. Then run `myos graph update <name>`.
- Graphs are optional: search and resume work fully without them.

## 9. Executive briefing
From the myOS folder (`cd C:\projects\myOS`) or any agent: **`/executive-briefing`**. It prints a compact table per
engagement, with every cell tagged **[V]** verified now, **[H]** historical (with age), **[I]** inferred, or **[M]** missing.
For the long version: `myos brief --detail`. To check every statement against its source: `python tests\verify_briefing.py`.

## 10. Recover after a configuration problem
- Agents stopped seeing myOS: `powershell -ExecutionPolicy Bypass -File C:\projects\myOS\scripts\install.ps1 -SkipVault`
- Interrupted save: `myos recover`
- Restore from backup: `docs/backup-and-recovery.md`
- Guard blocked something you really want: run it yourself in a terminal. For a deliberate deploy session, launch with
  `$env:MYOS_GUARD_ALLOW='production-host'` (that session only).

## Everyday commands (terminal)
```
myos list                      # engagements and projects
myos route [name]              # which project is this / where its facts live
myos resume <id>               # same as /resume-project
myos status <id>               # live repo state + last records
myos search "<terms>"          # scoped to this folder's engagement
myos brief                     # compact all-engagement briefing
myos graph list                # knowledge-graph corpora and approval state
myos manifest                  # what is installed (versions, files, approvals)
```
(`myos` is on your PATH in new terminals; otherwise use `python C:\projects\myOS\scripts\myos.py`.)
