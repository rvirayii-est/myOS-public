# myOS - Layer 0 orientation

You are inside **myOS**, the owner's personal AI operating system on this PC.
myOS is a router and memory system. It holds no product code.

## Where am I?
- myOS root: this folder. Routing table: `CONTEXT.md` (read it next).
- Obsidian vault (long-term memory): `vault` in `config/myos.json`. Never move, rename or bulk-rewrite it.
- Product repositories: `projects_root` and Orca worktrees in `orca_workspaces` (both in `config/myos.json`).
- CLI: `python scripts/myos.py <command>` (`list`, `route`, `status`, `resume`, `search`, `save`, `brief`, `verify`, `graph`).

## One home per fact
| Fact | Home |
| --- | --- |
| Code, commits, branches | the git repository |
| Issue / PR / release state | GitHub |
| Operational summary, next action, blockers | `projects/<id>.md` (ICM project card) |
| Decisions, session history, narratives | Obsidian vault |
| Computed relationships | Graphify output in `data/graph/` |
| Active agent sessions, worktrees | Orca |

Cards point to evidence; they do not copy histories. Unknown facts are written as `UNVERIFIED`.

## Hard rules
- Never invent status, test results, owners or deadlines. A test is "passed" only with captured evidence.
- Product repos: read-only unless the owner asks for work there. No resets, branch/worktree deletion,
  push, merge, deploys or live-database changes from myOS workflows.
- Keep engagements separate (see `engagements/`). Projects that share a name stay separate cards (see CONTEXT.md 3b).
- If the owner runs agents in bypass/Yolo mode, do not change permission settings. The myOS guard
  (`scripts/guard.py` hook, Codex `myos-guard.rules`) blocks destructive git and database operations and
  Graphify-gate bypasses, and asks before production-host changes, secret reads and cross-engagement access.
  Never try to evade it.
- Never send vault content to Graphify unless its corpus is approved (`myos graph list`).
  Agents never run `myos graph approve`; only the owner does, in their own terminal.
- Load little: card, then a handful of notes. Never read the whole vault.

## Workflows (single source: `workflows/*.md`)
/save-progress, /resume-project, /project-status, /context-search, /executive-briefing.
