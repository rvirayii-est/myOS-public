---
type: decision
project: lumen-ledger
status: accepted
created: 2026-01-10
tags: [synthetic, adr]
summary: Journal entries are stored as immutable events.
---
# ADR-001 Use event sourcing for journal (SYNTHETIC)

Context: auditors require that posted journal entries never change.
Decision: store every journal posting as an immutable event; balances are projections.
Consequence: corrections are reversal events, never edits. Depends on [[OrbitQueue]] ordering guarantees.
Alternatives rejected: mutable rows with an audit table.

Update 2026-03-01: the monthly reconciliation report replays journal events from the Archive Vault cold store.
