# myOS user guide (beginner friendly)

myOS is a small set of files and one command, `myos`. It gives every AI agent the same memory of your
projects. There is no server to start and nothing runs in the background.

> In the examples, `myos` means `python C:\projects\myOS\scripts\myos.py`.
> To type just `myos` in PowerShell, run this once:
> `[Environment]::SetEnvironmentVariable('Path', $env:Path + ';C:\projects\myOS\scripts', 'User')` and open a new terminal.

## 1. Start myOS
Nothing to start. Open Claude Code (or Codex) anywhere, in a terminal, in Orca, or in a project folder.
Every agent already knows about myOS through your user-level instructions. Quick check:
```
myos list          # engagements and projects
myos brief         # the whole portfolio, live
```

## 2. Open a project in Orca
1. In Orca, pick the repository (for example lumen-ledger) and open or create a worktree.
2. Launch Claude (or Codex) from the agent menu.
3. Ask it: *"What project is this and what's next?"* It runs `myos route` and finds the project card by itself.
   If you run agents in Yolo/bypass mode, The myOS guard still blocks destructive git and database
   operations, and asks before production changes (see agents.md).

## 3. Use Claude Code with myOS memory
| You type | What happens |
| --- | --- |
| `/resume-project lumen-ledger` | card, last sessions, recent notes, graph links, live git, then the next step. Changes nothing. |
| `/project-status` | live branch, commit and pending changes, plus the last recorded tests and blockers |
| `/context-search idempotency key bug` | the most relevant notes, with file paths and lines |
| `/executive-briefing` | every engagement: progress, blockers, approvals, recommendations |
| `/save-progress` | records this session in the vault and updates the card |

In Codex, use `$resume-project`, `$save-progress`, and so on.

## 4. Save progress
At the end of a working session, type `/save-progress`. The agent:
- figures out the project, reads the real git changes and the commands it actually ran,
- writes `03-PROJECTS/<Project>/sessions/<date>-<project>.md` in your vault,
- updates the card's "Latest handoff" (next actions, blockers, test evidence).
Running it twice in the same session updates the same record, so there are no duplicates. Tests without proof are
labelled `claimed-passed-NO-EVIDENCE`, never "passed".

## 5. Resume another project
`/resume-project orbit-queue`, or `cd` into its folder and type `/resume-project`. If the name is
ambiguous (for example several components share one repo), the agent asks you which one.

## 6. Search previous decisions
`/context-search <words>` or, in a terminal:
```
myos search "idempotency key" --project lumen-ledger
myos search "pg_dump restore" --type runbook
myos search "event sourcing" --type decision
```
Results list `path:line`. Graph links marked INFERRED are suggestions, not facts.

## 7. Refresh Graphify
```
myos graph list                     # corpora and approval state
myos graph plan vault-pilot         # see exactly what would be sent, and to whom
myos graph approve vault-pilot      # YOU, in your own PowerShell window (agents cannot do this)
myos graph build vault-pilot        # first build
myos graph update vault-pilot       # later: only changed notes are re-processed
```
To index more of the vault, add a corpus in `config\myos.json` (for example
`"include": ["03-PROJECTS/MyProject/**/*.md"]`), run `plan`, read the preview, then approve.
Outputs: `C:\projects\myOS\data\graph\<corpus>\graphify-out\` (`graph.html` opens in a browser).

## 8. Add a new repository
1. Copy an existing card, e.g. `projects\lumen-ledger.md` -> `projects\my-app.md`.
2. Edit the frontmatter: `id`, `name`, `engagement`, `aliases`, `repo`, `github`, `vault_folder`, `vault_hub`,
   `status_claim` and `status_source`. Use `UNVERIFIED` for anything you don't know.
3. Clear the generated blocks (leave the `<!-- myos:... -->` markers) and run `myos verify my-app`.
4. Add it to the table in `CONTEXT.md` and to its `engagements\<id>\ENGAGEMENT.md`.
5. Check it: `myos route my-app`.
   The `repo` field may be absolute or `@projects/<folder>` (under `projects_root` in `config/myos.json`).

## 9. Back up and restore
- Backup: `powershell -ExecutionPolicy Bypass -File C:\projects\myOS\scripts\backup.ps1`.
- Vault: commit it with git or Obsidian Sync. myOS never commits your vault.
- Restore and undo steps are in `docs\backup-and-recovery.md`.
- After a crash during a save: `myos recover`.

## 10. What needs you (manual intervention)
- Approve any Graphify corpus that contains real notes (`myos graph plan <corpus>`, then `myos graph approve <corpus>`),
  or use the guided `scriptseview-corpora.ps1` (see `docs\corpus-review-guide.md`).
- Check once that a guard **ask** really prompts you in your agent host. For example, ask the agent to
  `cat` a `.env` file and see whether a confirmation appears. If it doesn't, set
  `"ask_as": "deny"` in `config\guard.json`.
- When the guard blocks something you really want (e.g. a force-push), run it yourself in a terminal.
- Put your own production hosts in `config\guard.json` (`production_hosts`).

## 11. Projects that share a name
If two cards could match one word (e.g. a legacy and a new system), give each its own id and aliases and leave the shared
word out of both alias lists. The agent then asks which one you mean instead of mixing their histories.
