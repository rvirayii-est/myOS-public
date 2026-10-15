# myOS

A personal AI operating system for a Windows developer PC. Every coding agent (Claude Code or Codex, in
the Orca agent workspace or a plain terminal) knows which project it is in. It pulls a few relevant records instead of a whole notes vault, works
under safety guards that hold even in bypass/"Yolo" permission modes, and writes verified session history back to an
Obsidian vault.

```
request -> project identity (myos route) -> ICM card -> Graphify edges (approved corpora) -> Obsidian notes (path:line)
        -> live git (read-only) -> agent work (guarded) -> /save-progress -> vault session note + card handoff
```

- **No server, no database.** Plain Markdown and JSON plus one stdlib-only Python CLI (`scripts/myos.py`).
- **One home per fact.** Code state comes from git, history from the vault, and the operational summary from a small
  project card. Cards point to evidence; they never copy it.
- **Nothing invented.** Unknown facts are written `UNVERIFIED`. A test counts as passed only when its output was captured.
- **Engagements stay separate.** A session in one client's repository cannot search, resume or read another client's
  notes without the owner's confirmation.
- **Consent before transmission.** Notes reach an external model (Graphify semantic extraction) only for corpora the
  owner approved, in their own terminal, and only while the content is unchanged since that approval.

## Quick start (demo data included)
```powershell
git clone https://github.com/rvirayii-est/myOS-public.git C:\projects\myOS
cd C:\projects\myOS
python scripts\myos.py list                                   # three example engagements, three projects
python scripts\myos.py route lumen                            # alias routing
python scripts\myos.py search "event sourcing journal"         # search the bundled demo vault
python scripts\myos.py brief                                  # compact, source-tagged briefing
python -m unittest discover -s tests                          # 52 tests, all in throwaway temp folders
```
Everything ships pointing at **fictional** example data (`examples/demo-vault`, `projects/`, `engagements/`): Acme Corp,
Globex, Lumen Ledger and OrbitQueue are made up.

## Make it yours
1. **Config:** edit `config/myos.json`: `vault` (your Obsidian vault), `projects_root`, `orca_workspaces`.
   Paths accept `~`, `%VAR%` and paths relative to the myOS folder.
2. **Engagements and projects:** replace the examples in `engagements/` and `projects/` (see `docs/user-guide.md` §8).
   A card's `repo` can be absolute or `@projects/<folder>`.
3. **Guard:** put your production hosts in `config/guard.json` (`production_hosts`).
4. **Agents:** `powershell -ExecutionPolicy Bypass -File scripts\install.ps1`. It backs up every file it touches, then
   installs the five skills, a marker-delimited block in `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`, the Claude
   PreToolUse guard hook and the Codex guard rules. Undo with `scripts\uninstall.ps1`.
5. **Graphify (optional):** create `graphify\.venv` with `pip install graphifyy`, then follow `docs/graphify.md`.

## Docs
| | |
| --- | --- |
| Daily workflow (Orca, resume, search, save, Claude <-> Codex, graphs, briefing, recovery) | [docs/daily-workflow.md](docs/daily-workflow.md) |
| Beginner guide | [docs/user-guide.md](docs/user-guide.md) |
| Architecture | [docs/architecture.md](docs/architecture.md) |
| Security and guards | [docs/security-and-guards.md](docs/security-and-guards.md) |
| Agents (Claude Code, Codex, Orca) | [docs/agents.md](docs/agents.md) |
| Graphify and corpus approval | [docs/graphify.md](docs/graphify.md), [docs/corpus-review-guide.md](docs/corpus-review-guide.md) |
| Backup and recovery | [docs/backup-and-recovery.md](docs/backup-and-recovery.md) |
| Ponytail A/B benchmark | [docs/ponytail-benchmark.md](docs/ponytail-benchmark.md) |

## Everyday commands
In an agent: `/resume-project`, `/context-search <terms>`, `/project-status`, `/save-progress`, `/executive-briefing`
(Codex: `$resume-project` and so on).
In a terminal: `myos list | route | resume <id> | status <id> | search "<terms>" | brief | graph list | manifest`.

## Layout
`CLAUDE.md`/`AGENTS.md` (Layer 0) · `CONTEXT.md` (routing) · `engagements/`, `projects/` (ICM cards) · `workflows/` ·
`skills/` · `schemas/` · `scripts/` (CLI, guard, installer, backup/restore, corpus review) · `bin/` (Codex shim) ·
`templates/obsidian/` · `graphify/shim/` (hardened extraction shim) · `config/` · `examples/demo-vault/` · `tests/` · `docs/`.
Generated and private data (`data/`, `logs/`, `backups/`, approvals) is git-ignored.

## Requirements
Windows 10/11, Python 3.10+, Git, PowerShell. Optional: Claude Code, Codex CLI, Orca, Obsidian, Graphify (`graphifyy`).
