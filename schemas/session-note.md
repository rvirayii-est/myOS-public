# Session note schema (vault `03-PROJECTS/<Project>/sessions/<yyyy-mm-dd>-<id>.md`)

One file per project per day. Each session is one section delimited by
`<!-- myos:session:begin id=<sid> -->` ... `<!-- myos:session:end id=<sid> -->`.
Saving again with the same `sid` replaces that section, so records are not duplicated.

Section headings (fixed, parsed by `myos status/resume`):
Summary · Repository evidence (captured at save time) · Changes made · Tests · Decisions (agent-recorded - review
before treating as accepted) · Bugs and blockers · Next actions · Pending approvals · Gaps in this record.

Test results: passed | failed | partial | not-run | skipped | unknown | claimed-passed-NO-EVIDENCE.
