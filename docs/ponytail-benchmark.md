# Ponytail A/B benchmark (measured 2026-10-15)

**Decision: Ponytail lite stays ON by default** (`%APPDATA%\ponytail\config.json` -> `"defaultMode": "lite"`). Every decision
criterion was met in this bounded test. The raw data and harness touch private repositories, so they are not published.

## Setup (identical for both arms)
- **Tasks:** one real feature in each of three private products, each in a **disposable fixture**. The module and its tests were exported read-only
  with `git show HEAD:<path>` into scratch; no repository or worktree was touched.

  | Product | Fixture | Task | Graded by |
  | --- | --- | --- | --- |
  | App A | money module (Rust) | `Money::allocate(weights)`, largest-remainder exact split | `cargo test` + 8 held-out tests |
  | App B | clock module (Rust) | business-day range at a fixed UTC offset | `cargo test` + 4 held-out tests |
  | App C | CSV helper (TypeScript) | `csvTable()` + quote `\r` cells | `node --test` + 4 held-out tests |
- **Arms:** A = `PONYTAIL_DEFAULT_MODE=off`, so the hook injects nothing. B = `lite`. Everything else was the same: the same
  Claude Code 2.1.300 with the owner's settings (model, effort, Yolo `--dangerously-skip-permissions`), the same prompt, tools,
  starting files and warm build cache, and myOS active in both.
- **Budget:** 3 tasks × 2 arms × 2 repetitions = 12 runs, about $3.40 in total.
- **Grading:** held-out tests the agent never saw, plus the agent-visible test command.

## Results
| Task | Time | Output tokens | Cache reads | Cost | Tool calls | Lines added | Held-out |
| --- | --- | --- | --- | --- | --- | --- | --- |
| App C CSV | 100 s -> 74 s (-26%) | 8,941 -> 7,212 (-19%) | -33% | $0.693 -> $0.601 (-13%) | 22 -> 20 | 41 -> 27 | 8/8 -> 8/8 |
| App B business day | 50 s -> 46 s (-8%) | 4,622 -> 3,907 (-15%) | -17% | $0.548 -> $0.537 (-2%) | 8 -> 8 | 104 -> 87 | 8/8 -> 8/8 |
| App A allocate | 67 s -> 53 s (-21%) | 6,404 -> 4,858 (-24%) | -39% | $0.531 -> $0.478 (-10%) | 8 -> 4 | 164 -> 128 | 16/16 -> 16/16 |
| **Total** | **217 s -> 172 s (-20.5%)** | **19,967 -> 15,977 (-20%)** | **-31%** | **$1.77 -> $1.62 (-8.8%)** | 38 -> 32 | 309 -> 242 | **32/32 -> 32/32** |

- Lite was cheaper **and** produced fewer output tokens in **6 of 6** paired runs.
- Visible tests passed in all 12 runs.
- **Test coverage check:** lite wrote fewer test *functions* (App C 1 vs 2 new; App A 4-5 vs 6), but reading them shows the
  same cases packed into fewer functions: ties, negative amounts, zero weights, zero amount, the `i64::MIN` extreme, and all three
  panic cases; both CSV requirements. App B was equal (3 vs 3).

## The four consumption layers
| Layer | Measured | Notes |
| --- | --- | --- |
| 1. Static prompt overhead | myOS global block ~197 tokens + 5 skill descriptions ~352 tokens (both arms). **Ponytail lite ruleset +3,058-3,079 chars (~770 tokens)**, injected once per session (verified: 1 injection, no duplicates) | Cache-write tokens were the same in both arms (-0.8%): the extra rules are cheap after caching |
| 2. Historical context retrieved | Not exercised in the A/B (fixtures sit outside registered projects). Separately measured: `route` ~139 tokens, `search` ~497, `status` ~883, `resume` ~1,298, `brief` compact ~829 (detail ~3,305) | The whole vault would be ~810,000 tokens; a resume retrieves ~0.16% of it |
| 3. Agent reasoning and tool use | Output -20%, tool calls -16%, cache reads -31% | This is where Ponytail saves |
| 4. Total session | Cost -8.8%, time -20.5% | |

## Limitations (read before generalising)
- Only 2 repetitions per task, so the effect sizes are indicative, not statistically established. They are consistent in direction.
- The tasks were small, well-specified features. Larger, exploratory tasks were not measured.
- Cost uses Claude Code's reported `total_cost_usd`. On a subscription plan, treat cost as relative.
- Codex was not benchmarked. Codex has the plugin's skills, but its lifecycle hooks are inactive until you trust them.
- Ponytail's own published numbers (-45% tokens, -26% cost) were **not** reproduced; this test measured -20% output and -8.8% cost.

## Toggle Ponytail
| Where | How |
| --- | --- |
| This session (Claude or Codex) | `/ponytail lite`, `/ponytail full`, `/ponytail ultra`, `/ponytail off` (Codex: `$ponytail:ponytail`); `/ponytail` shows the level |
| Default for new sessions | edit `%APPDATA%\ponytail\config.json` -> `{"defaultMode": "lite"}` (or `off` / `full` / `ultra`) |
| One launch only | set `PONYTAIL_DEFAULT_MODE=off` in that terminal before starting the agent (PowerShell: `$env:PONYTAIL_DEFAULT_MODE='off'`) |
| Disable the plugin | `claude plugin disable ponytail@ponytail` (re-enable: `claude plugin enable ponytail@ponytail`) |
| Remove completely | `claude plugin uninstall ponytail@ponytail`, and `codex plugin remove ponytail`; for Orca's Codex, run it with `$env:CODEX_HOME="$env:APPDATA\orca\codex-runtime-home\home"` |
