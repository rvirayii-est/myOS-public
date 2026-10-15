# myOS - instructions for Codex and other AGENTS.md agents

This file mirrors `CLAUDE.md` for agents that read AGENTS.md. Both say the same thing, and
the details live in the files referenced below. Do not duplicate them here.

1. Read `CLAUDE.md` (Layer 0 orientation and hard rules), then `CONTEXT.md` (routing).
2. Identify the project with `python scripts/myos.py route` (from the myOS folder, or with its full path).
3. Workflows are in `workflows/*.md`: save-progress, resume-project, project-status,
   context-search, executive-briefing. Follow the procedure file exactly. In Codex they are
   available as skills `$save-progress`, `$resume-project`, `$project-status`,
   `$context-search` and `$executive-briefing`.

Hard rules (same as CLAUDE.md): no invented facts, no unevidenced "passed" tests, product
repos are read-only for myOS workflows, engagements stay separate, and no vault content goes
to Graphify unless the corpus is approved by the owner.
