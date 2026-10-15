# Workflow - Project Status (`/project-status`, Codex `$project-status`)

1. Identify the project (argument, else `myos route`).
2. Run `myos status <id>`.
3. Report in this shape, keeping LIVE and HISTORICAL apart:
   - Verified current state (LIVE, checked now): branch, commit, pending changes, upstream ahead/behind.
   - Latest significant work (HISTORICAL, with date and source).
   - Last known test evidence, with command and result exactly as recorded, or "none recorded".
   - Open blockers, next steps, pending approvals.
   - Evidence references (file paths).
4. GitHub issue/PR state: only if the owner asks and `gh` is authenticated. Use read-only
   `gh issue list` / `gh pr list -R <github>` and cite it as live GitHub evidence.
5. Never upgrade a claim: "README says released" is not "released".
