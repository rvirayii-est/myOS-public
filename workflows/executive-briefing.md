# Workflow - Executive Briefing (`/executive-briefing`, Codex `$executive-briefing`)

1. Run `myos brief`. This is the compact table (about 830 tokens), with every cell tagged [V]/[H]/[I]/[M] and checked by
   `tests/verify_briefing.py`. Use `myos brief --detail` for the long labelled form (about 3,300 tokens), and add `--cached`
   to skip live git.
2. Present engagement by engagement: active projects, last known progress (with dates),
   pending approvals, blockers, overdue items (only where a record states a due date),
   upcoming milestones (only if recorded).
3. Put "Suggested priorities" last and label each one RECOMMENDATION. Base each on a fact shown
   above it (uncommitted work, no upstream, stale record, blocker).
4. Never invent deadlines, owners or client commitments. Missing means "not recorded".
