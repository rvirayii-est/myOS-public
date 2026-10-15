---
name: save-progress
description: myOS - save the current session's verified progress for the current project. It writes a dated Obsidian session note, updates the ICM project card, and runs an incremental Graphify update when that is permitted. Use when the user says /save-progress, "save progress", "record this session", or "update myOS".
---
# /save-progress (myOS)

Follow `C:\projects\myOS\workflows\save-progress.md` exactly. Read it first.

Essentials, if that file cannot be read:
- CLI: `python "C:\projects\myOS\scripts\myos.py"`. Run it from this session's working directory.
- `myos route --json` identifies the project. If there are zero or several candidates, ask the user.
- Gather facts with read-only git (`status`, `diff --stat`, `log`) and from commands actually run in this conversation.
- Write JSON to `C:\projects\myOS\logs\inbox\save-<project>-<timestamp>.json`, then run `myos save --input <file>`.
- Session id for this Claude Code session: `claude-${CLAUDE_SESSION_ID}`. If that still shows a literal `${...}`, omit `session_id`.
- A test is "passed" only with quoted output evidence. Declare anything you could not see under `gaps`.
- Never commit, push, or approve Graphify corpora.
