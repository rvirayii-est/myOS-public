# Workflow - Save Progress (`/save-progress`, Codex `$save-progress`)

Purpose: turn the current session into a verified, dated Obsidian session record and refresh the
project's ICM card. Re-running it in the same session updates the same record (no duplicates).

CLI: `python C:\projects\myOS\scripts\myos.py` (below: `myos`).

## Inputs
| Source | What | Why |
| --- | --- | --- |
| `myos route --json` (run in the session's working directory) | project id, card, vault folder | identify the project |
| `git status`, `git diff --stat`, `git log -10 --oneline` in the working tree | actual changes | facts, not memory |
| this conversation | commands you ran and their real output | test evidence, decisions, blockers |

## Process
1. Run `myos route --json`. If it returns zero or several candidates, ask the owner which project
   (offer the candidate ids). Never guess between components that share a repository. If you cannot ask (non-interactive run), do not
   save; report the candidates and stop. A record filed under the wrong project is worse than no record.
2. Inspect the working tree with read-only git commands. Do not stage, commit, stash or push.
3. Build the record from evidence only:
   - `changes`: what actually changed, which you confirmed from the diff or the conversation.
   - `tests`: only commands actually executed in this session. `result` is one of
     passed | failed | partial | not-run | skipped | unknown. `evidence` must quote the real
     output line (for example "Tests: 41 passed, 0 failed"). With no evidence the CLI downgrades
     `passed` to `claimed-passed-NO-EVIDENCE`. Never write passed for a test you did not see pass.
   - `decisions`: {decision, rationale}. These are recorded as agent-recorded proposals. Say in the
     rationale if the owner explicitly confirmed it.
   - `bugs`, `blockers`, `next_actions`, `pending_approvals`: concrete and short.
   - `gaps`: anything you could not see, for example "context was compacted; early steps known
     only from summary", "owner ran tests outside this session - results unknown".
4. Use forward slashes in any paths inside the JSON (e.g. `C:/projects/x`). The CLI tolerates single backslashes,
   but forward slashes avoid escaping mistakes. Write the JSON to `C:\projects\myOS\logs\inbox\save-<project>-<yyyyMMdd-HHmm>.json`:
   ```json
   {"project": "<id>", "agent": "claude-code|codex", "session_id": "<stable id for this session>",
    "summary": "...", "changes": [], "tests": [{"command": "", "result": "", "evidence": ""}],
    "decisions": [{"decision": "", "rationale": ""}], "bugs": [], "blockers": [],
    "next_actions": [], "pending_approvals": [], "gaps": []}
   ```
   Use the same `session_id` every time you save in this session. If you have no session id, omit
   it; the CLI then uses one record per project, agent and day.
5. Run `myos save --input <that file>` from the session's working directory.
   It writes atomically through a recovery journal (see `myos recover`).
6. If the output says an approved corpus covers the note, run `myos graph update <corpus>`.
   Otherwise report "Graphify: skipped (not approved)". Never approve corpora yourself.
7. Report to the owner the session note path, the card path, and anything recorded under gaps.

## Outputs
- Vault: `03-PROJECTS/<Project>/sessions/<yyyy-mm-dd>-<id>.md` (one file per project per day,
  one section per session id).
- Card: `projects/<id>.md` blocks `live`, `handoff` and `sessions` are regenerated. Human sections
  are untouched.

## Audit
- No test is marked passed without evidence.
- No product-repo files were modified by the workflow itself.
- A re-run produced "files changed: none" or replaced the same session section.
