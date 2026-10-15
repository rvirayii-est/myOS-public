# Workflow - Resume Project (`/resume-project`, Codex `$resume-project`)

Purpose: pick a project back up from persistent memory, read-only.

## Process
1. Identify the project: the argument if given, else `myos route` from the current directory.
   - **Ambiguous** (e.g. a monorepo root that maps to several component cards): if you can ask the owner,
     ask. If you cannot (headless/non-interactive run), **do not pick one**. List the candidate ids, show the live repo
     state once, and stop with "re-run /resume-project <id>". Branch names are not evidence of which product is meant.
   - Unknown: say so and show `myos list`.
2. Run `myos resume <id>`. It prints, in order: card, recent myOS sessions, the most recent
   vault notes, related graph context, live repository state, and the latest handoff.
3. Open at most 3-5 source notes that the output points to and that matter for the next step.
   Do not read whole folders.
4. Answer with:
   - **Where it stands**: live git facts (branch, HEAD, uncommitted count), labelled LIVE.
   - **Last work**: from the latest session/handoff, labelled with its date.
   - **Next actionable step**: one concrete step, citing where it came from.
   - **Blockers and unresolved decisions**.
   - **Stale or conflicting records**: say so explicitly when notes disagree with live state.
5. Do not edit code, notes or the card during a resume.
6. A card's `repo` is the project's **main repository**, never a worktree. Worktrees (Orca's, `.claude/worktrees`) appear in
   the card's live block with their branches. If the active work is in a worktree, say so; do not propose changing `repo`.
