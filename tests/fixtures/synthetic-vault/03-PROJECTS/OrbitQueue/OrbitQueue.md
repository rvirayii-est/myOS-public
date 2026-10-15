---
type: project-hub
project: orbit-queue
engagement: synthetic
tags: [synthetic]
summary: SYNTHETIC fictional message relay with at-least-once delivery.
---
# OrbitQueue (SYNTHETIC)

OrbitQueue is a fictional at-least-once message relay. Consumers must be idempotent.
It is used by [[00-Overview|Lumen Ledger]] for journal sync.
Ordering is guaranteed per partition key only.
