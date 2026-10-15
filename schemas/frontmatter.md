# Standard frontmatter (new notes only)

Apply to notes that myOS creates and to notes created from `07-TEMPLATES/myOS`. Existing notes are
**not** rewritten to conform. Their existing keys (`Status`, `Area`, `Type`, `Date`, ...) stay valid.

| Key | Required | Values / format |
| --- | --- | --- |
| type | yes | project-hub, session, decision, bug-investigation, release-verification, meeting, handoff, lessons, project-card, engagement |
| project | yes* | project-card id, e.g. `lumen-ledger` (*not for engagement-level notes) |
| engagement | yes | an id from `engagements/` (e.g. acme, globex, personal) |
| created | yes | YYYY-MM-DD |
| updated | yes | YYYY-MM-DD or ISO timestamp |
| status | yes | draft, active, proposed, accepted, superseded, recorded, resolved, open |
| tags | yes | inline list `[a, b]` |
| summary | yes | one sentence |

The parser (`scripts/myos.py`) supports scalars and inline `[lists]` only. Avoid nested YAML.
