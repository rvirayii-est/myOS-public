---
type: project-hub
project: lumen-ledger
engagement: synthetic
status: active
tags: [synthetic, test]
summary: SYNTHETIC test project - a fictional offline-first bookkeeping app.
---
# Lumen Ledger (SYNTHETIC)

Lumen Ledger is a fictional offline-first bookkeeping app used only to test myOS.

- Backend: Rust + Axum API talking to PostgreSQL.
- Client: Vue 3 desktop shell built with Tauri.
- Sync: uses the [[OrbitQueue]] message relay to push journal entries.
- Decision record: [[ADR-001 Use event sourcing for journal]]
- Runbook: [[PostgreSQL backup runbook]]
