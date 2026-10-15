# Agents: Claude Code, Codex, Orca

## Permission model
myOS assumes the owner may run agents in bypass mode (Orca "Yolo": Claude with `--dangerously-skip-permissions`, Codex with
`--dangerously-bypass-approvals-and-sandbox`, or Claude Code's global `defaultMode: bypassPermissions`).
myOS does **not** change permission settings. Safety comes from the **myOS guard**, which works inside bypass modes.

## What `scripts\install.ps1` installs (all reversible with `scripts\uninstall.ps1`; originals saved in `backups\`)
| Agent | Mechanism | File |
| --- | --- | --- |
| Claude Code (any folder) | marker-delimited myOS block in user instructions | `~\.claude\CLAUDE.md` (content outside the markers untouched) |
| Claude Code | 5 user skills: `/save-progress`, `/resume-project`, `/project-status`, `/context-search`, `/executive-briefing` | `~\.claude\skills\<name>\SKILL.md` |
| Claude Code | **guard hook**: PreToolUse -> `python <myOS>/scripts/guard.py` (matcher Bash, PowerShell, Read, Edit, Write, MultiEdit, NotebookEdit, Grep, Glob) | `~\.claude\settings.json` (one entry added; other hooks and `defaultMode` untouched) |
| Codex (terminal) | myOS block | `~\.codex\AGENTS.md` |
| Codex (Orca) | myOS block. Orca sets `CODEX_HOME` to its own home. | `%APPDATA%\orca\codex-runtime-home\home\AGENTS.md` (if present) |
| Codex (both) | the same 5 skills (`$save-progress`, ...) | `~\.agents\skills\<name>\SKILL.md` |
| Codex (both homes) | **guard exec-policy rules** (`forbidden`) | `rules\myos-guard.rules` in each Codex home; existing rules untouched |

Nothing is written into any product repository.

## myOS guard
| Decision | Covers |
| --- | --- |
| **deny** (blocked in every mode) | force-push and remote branch deletion; `git reset --hard`; `git clean -f`; `git branch -D`; `git worktree remove --force`; `git stash clear`; history rewrites; recursive delete of protected roots (drive, `projects_root`, any repo or worktree root, `.git`, the vault and its top folders, `~\.claude`, `~\.codex`, Orca data, myOS); destructive SQL when a DB client is in the command; `flyway clean`, `supabase db reset`, `dotnet ef database drop`, etc.; running Graphify directly (it must go through `myos graph`); `myos graph approve`; uploading a secret file |
| **deny, fail-closed** | mutating commands (ssh, scp, rsync, psql, POST/PUT/DELETE) against the `production_hosts` in `config\guard.json`. Owner override per session: launch the agent with `MYOS_GUARD_ALLOW=production-host`. |
| **ask** (owner confirms) | reading `.env`, keys or credentials; `git add` of secret files; discarding all changes; soft branch or worktree deletion; deploy and infra commands; editing the guard itself; **cross-engagement access** (files, `myos` queries via `--project`, `--cwd`, `cd` into myOS, `--all-engagements`, `myos brief`, vault-wide or `projects_root`-wide searches) |
| allow | everything else, including normal `git push`, builds, tests, `rm -rf node_modules/dist/target`, `cp .env.example .env` and health-check GETs |

Codex rules are prefix-based and cover the git/DB/Graphify subset. Flags written in another order may slip
through. The Claude hook is regex-based and broader.

Config: `config\guard.json`. Decisions are logged to `logs\guard.log`, with secrets redacted. To disable for one
session, launch the agent with `MYOS_GUARD=off` in its environment. The agent cannot set this itself.
Fail-open: a guard error never blocks work.

## What was verified (on the author's machine, with synthetic files and throwaway repos only)
- A headless Claude session in bypass mode was blocked on `git reset --hard`, `cat .env` and a cross-engagement Read.
- Codex with `--dangerously-bypass-approvals-and-sandbox` was blocked on `git reset --hard`, `git stash clear`
  and the canary, and `git status` still ran. Codex launched inside Orca honoured the rules.
- **ask in an interactive Orca Yolo session:** the tab showed *"Hook PreToolUse:Bash requires confirmation … Do you want to
  proceed?"*; answering No stopped it, and the synthetic secret never reached the transcript.
- **headless `-p`:** ask fails closed (blocked).
- **Not reliable in every host:** in one non-Orca harness, ask-flagged commands proceeded without a visible prompt. That is
  why production hosts are **deny** with a per-session override, and why `"ask_as": "deny"` exists in `config\guard.json`.
- **False positives fixed:** quoted text and heredoc bodies are data; regex/glob patterns are not file paths; recursive-delete
  checks only look at the delete's own command segment. Shell code is still checked (`bash -c`, `pwsh -Command`,
  `ssh host "…"`, shell heredocs).
- **Cross-engagement leak found and closed:** an agent in client B's repo answered a search by running
  `cd <myOS>; myos search … --project <client A project>`. The guard rule `cross-engagement-query` now asks first, and
  search/graph context are scoped to the session's engagement by default.

## Notes for Windows setups
- **Codex CLI version:** if an old standalone `codex.exe` shadows the npm build on PATH, put `bin\` (which forwards to
  `%APPDATA%\npm\codex.cmd`) before it in your user PATH.
- **Codex read-only sandbox in Orca:** some Codex builds cannot spawn the Store-packaged `pwsh.exe` under
  `--sandbox read-only`; `workspace-write` works.
- **Optional session-end reminder:** `myos remind` can be wired as a Claude `Stop` hook. It is not installed by default.
