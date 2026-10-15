# Workflow - Context Search (`/context-search`, Codex `$context-search`)

1. Turn the request into 1-4 distinctive terms (feature, technology, error text, decision topic,
   dependency). Add `--project <id>` when it concerns one project and
   `--type decision|session|bug|runbook|spec` when it fits.
2. Run `myos search "<terms>" [--project id] [--type t] [--limit 8]`.
   It searches only approved vault folders (`config/myos.json` -> search.include; personal
   01-LIFE is excluded) plus project cards, redacts secrets in snippets, and appends Graphify
   relationships when a built graph matches.
3. Open only the top 2-4 notes needed to answer. Quote the source path and line for every claim.
4. Graph edges: EXTRACTED edges come from the note text. INFERRED and AMBIGUOUS edges are model
   hypotheses. Present them as "possibly related", never as facts, and verify against the note.
5. If nothing matches, say so and suggest other terms. Do not fall back to reading whole folders.
