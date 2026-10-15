---
name: context-search
description: myOS - search approved Obsidian notes, project cards and Graphify relationships for past decisions, features, technologies, dependencies, errors and historical issues. Returns source paths. Use for /context-search, "did we decide…", "where did we document…", "have we seen this error before".
---
# /context-search (myOS)

Follow `C:\projects\myOS\workflows\context-search.md`.

- Run `python "C:\projects\myOS\scripts\myos.py" search "<terms>" [--project <id>] [--type decision|session|bug|runbook|spec]`.
- Open only the top 2-4 hits you need, and cite path:line for each claim.
- INFERRED and AMBIGUOUS graph edges are hypotheses, not facts.
