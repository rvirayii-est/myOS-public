# myOS - Layer 1 routing

Read top to bottom and stop as soon as you have enough context.

## 1. Which project?
Run `python scripts/myos.py route [name]` (from the myOS folder, or with its full path).
- With no name it detects the project from the current directory (works in Orca and
  `.claude/worktrees` worktrees because it maps any worktree to its main repository).
- Ambiguous (e.g. several component cards share one repo)? Ask the owner which one.
- `myos list` shows every engagement and project.

## 2. Routing table
| Need | Go to | Layer |
| --- | --- | --- |
| Engagement boundary and projects | `engagements/<id>/ENGAGEMENT.md` | 2 |
| Project summary, next action, blockers, pointers | `projects/<id>.md` | 2 |
| Current code state | `myos status <id>` (live, read-only git) | 4 |
| History, decisions, past sessions | vault paths named in the card; `myos resume <id>` | 4 |
| Find a past decision, error or dependency | `myos search "<terms>" [--project id] [--type decision]` | 4 |
| Related concepts | Graphify section of `myos search` output (hypotheses unless EXTRACTED) | 4 |
| How to run a workflow | `workflows/<name>.md` | 2 |
| Schemas for cards and notes | `schemas/` | 3 |
| Security and exclusion rules | `config/exclusion-policy.json`, `docs/security-and-guards.md` | 3 |

## 3. Engagements (example data - replace with your own)
| id | Engagement | Projects |
| --- | --- | --- |
| acme | Acme Corp (example client) | lumen-ledger |
| globex | Globex (example client) | orbit-queue |
| personal | Personal | myos-sandbox (test fixture) |

## 3b. Disambiguation rules
Record owner decisions about ambiguous names here, for example:
- "Foo Legacy and Foo v2 are separate projects. A bare 'Foo' is ambiguous: ask which one, never merge their histories."
- "Repo `monorepo` owns components A, B and C; route by subfolder."

## 4. Instructions and permissions that apply
1. The repository's own `CLAUDE.md` / `AGENTS.md` govern work inside that repository.
2. myOS rules (`CLAUDE.md` here) govern memory, routing and records.
3. When they conflict about code, the repository wins. When they conflict about records or
   external transmission, myOS wins.
