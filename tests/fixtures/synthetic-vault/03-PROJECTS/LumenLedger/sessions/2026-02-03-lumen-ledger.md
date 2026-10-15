---
type: session
project: lumen-ledger
created: 2026-02-03
tags: [synthetic, session]
summary: Fixed duplicate posting bug caused by retry without idempotency key.
---
# Session 2026-02-03 (SYNTHETIC)

Bug: duplicate journal postings when the client retried after a timeout.
Root cause: the sync push lacked an idempotency key, so [[OrbitQueue]] redelivered.
Fix: added ClientRequestId dedupe in the posting handler.
Tests: `cargo test posting::idempotency` passed (12 passed, 0 failed).
Next: add a reconciliation report.
