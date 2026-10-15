---
name: resume-project
description: myOS - resume a project from persistent memory (ICM card, recent Obsidian sessions, Graphify context, live repo state) and name the next actionable step, blockers and open decisions. Read-only. Use for /resume-project, "resume <project>", "where was I on <project>", "pick up <project>".
---
# /resume-project (myOS)

Follow `C:\projects\myOS\workflows\resume-project.md`.

- Project = the argument (`$ARGUMENTS`) if given, else detected by `python "C:\projects\myOS\scripts\myos.py" route`.
- Run `python "C:\projects\myOS\scripts\myos.py" resume <id>`, then open at most 3-5 of the notes it points to.
- Read-only: do not modify code, notes or cards.
- Label LIVE facts (checked now) separately from HISTORICAL ones (dated records), and flag any conflicts.
