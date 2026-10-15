---
name: executive-briefing
description: myOS - engagement-by-engagement operational briefing across every registered engagement. Covers active projects, last progress, pending approvals, blockers, recorded due dates, and clearly labelled recommendations. Use for /executive-briefing, "brief me", "portfolio status".
---
# /executive-briefing (myOS)

Follow `C:\projects\myOS\workflows\executive-briefing.md`.

- Run `python "C:\projects\myOS\scripts\myos.py" brief`. It prints a compact table where every cell is tagged
  [V]erified / [H]istorical / [I]nferred / [M]issing. Add `--detail` only if the owner asks for the long form.
- Present it as given: keep the tags, and don't merge or embellish. Label your own suggestions as RECOMMENDATION.
- From a project tab this asks for confirmation, because it spans engagements. Running it from `C:\projects\myOS` does not.
- Never invent deadlines or owners.
