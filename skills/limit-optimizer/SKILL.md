---
name: limit-optimizer
description: Use when a Claude Code user is burning through their usage limits (weekly/5-hour) too fast, asks "why are my limits gone", wants to reduce token/limit consumption, or wants a usage/context/cost audit. Diagnoses from their REAL data (transcript parse + /context + /usage + /doctor), then applies evidence-based optimizations that never sacrifice quality. Triggers: "limits gone", "burning limits", "reduce usage", "usage audit", "why so expensive", "optimize claude code cost", "context too big", "hitting weekly limit".
---

# Limit optimizer

Diagnose why a Claude Code user hits their limits early, then optimize — from **measured data**, not vibes.
The guiding filter throughout: **cut waste, never work.** A token is waste if it re-processes junk or over-powers a mechanical task; it's work if it thinks on something that matters. Optimize the former; never touch the latter.

Pairs with the `cost-aware-runner` skill: this one **diagnoses + sets up** (one-time); that one is the **ongoing execution policy** (routing + nightly runner).

## How limits actually work (get this first)
- **Two independent meters.** 5-hour = a rolling RATE window (resets every 5h, shows only your last 5h). Weekly = a cumulative TOTAL (all bursts since reset, doesn't roll off). Low 5-hour tells you nothing about weekly — weekly is the sum of every past burst. On Max there's also a **separate weekly Opus cap**.
- **The weekly cap is COST-WEIGHTED, not a token count.** Fable ≈ 10×, Opus ≈ 5×, Sonnet ≈ 3×, Haiku = 1× per token. Frontier-heavy work fills it 5-10× faster than raw tokens suggest.
- **Why weekly dies while 5-hour stays green:** parallel sessions/subagents = many frontier streams at once (compute-hours ≫ wall-clock hours), long/overnight sessions = sustained spend, all summing into weekly while each rolling 5h window stays under its (generous, doubled-May-2026) cap.
- **Fast mode does NOT touch the weekly limit** on subscriptions — it's usage-credits only (real $, 2× price, same model = same quality, ~2.5× faster). Off-limit by design. Irrelevant to weekly burn.

## Phase 0 — Interview (shape the advice)
Ask before optimizing:
1. **Plan?** Pro / Max 5x / Max 20x / Team. (Sets the cap size + whether an Opus sub-cap applies.)
2. **Which meter hurts?** Weekly or 5-hour? (Usually weekly — check `/usage`.)
3. **Quality bar?** Is frontier (Opus/Fable) required on cognition, or is downgrading acceptable? (Most power users: frontier on everything that *thinks*; retrieval can always drop.)
4. **Work modes?** Interactive coding / research / overnight-autonomous / heavy parallelism? (Each has different top levers.)

## Phase 1 — Measure the ground truth
1. **Run the parser** (self-contained, reads `~/.claude/projects/**`):
   `python3 scripts/analyze_usage.py [tz_offset_hours]`
   → burn by model, token-type split, main-vs-subagent, context-size distribution, cache economics, by-hour/night, whale sessions, actual MCP/skill/agent usage, and auto-flagged signals.
2. **Have the USER paste (you can't see these live):**
   - `/context` — the per-category window breakdown (Memory / MCP / System tools / Messages / deferred). Confirms what sits in every turn.
   - `/usage` — the 3 bars (5h / weekly-all / weekly-Opus) + reset times. Shows how close and which cap binds.
   - `/doctor` — flags stale installs, unused MCP servers, hook health.

## Phase 2 — Diagnose (read the signals)
| Signal | Meaning | Lever |
|---|---|---|
| cache_read >90% of tokens | burn = context × turns × price; output is noise | context hygiene (biggest, quality-POSITIVE) |
| frontier >80% of burn | paying frontier price on retrieval too | route retrieval → Haiku |
| subagents >20%, mostly frontier | fan-out workers inherit Opus/Fable | pin workers by role |
| >30% turns over 200K | sessions ballooning (accumulation, not need) | cap window; discrete-task nights |
| >30% burn at night | overnight autonomous is a top driver | discrete-task runner + anti-runaway |
| cache_write large share | big file reads / verbose output written at 2× | targeted reads, delegate verbose to subagents |
| /context: big Memory/MCP/plugin blocks | always-loaded tax every turn | prune unused plugins/MCP; keep memory (recall = quality) |

## Phase 3 — Optimize (quality-filtered)
Apply in impact order. **A = zero/positive quality cost (do freely); B = reconsider; C = don't (trades quality).**

**A — pure waste (often quality-POSITIVE):**
- **Cap the context window** — `settings.json` `env: { "CLAUDE_CODE_DISABLE_1M_CONTEXT": "1", "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "80" }`. Stops the 700K-950K balloon; auto-compacts before context-rot (frontier @150K > frontier @700K). Existing `PreCompact` hooks checkpoint state to disk, so nothing is lost. Escape hatch for a genuine huge-context task: launch that session with `CLAUDE_CODE_DISABLE_1M_CONTEXT=0`.
- **Route retrieval → Haiku** (grep/read/nav/`ls`/run-test/triage-summary). A photocopier — frontier returns the same bytes. Pin per-role subagents (frontmatter `model:`); reviewers/cognition stay Opus/Fable.
- **Delegate verbose reads to a subagent** that returns a summary → keeps the main loop lean (kills the cache-write tax). Works even with frontier subagents — the win is **context isolation**, not the cheaper model.
- **Overnight as discrete tasks**, not one long `/loop` — each item its own fresh context (never balloons; no mid-run compaction). Use `cost-aware-runner` / `nightly-runner`.
- **Fewer parallel heavy sessions**, or make parallel workers cheap.
- **Prune unused plugins/MCP** (the parser's "actual usage" + `/doctor` show which are never invoked). Removes always-loaded skill/agent/tool descriptions.

**B — reconsider (small quality risk):**
- Global `effort=medium` or `MAX_THINKING_TOKENS` caps — usually the WRONG trade: thinking is a tiny % of a cache-read-dominated bill, but caps hurt the hardest tasks. Skip unless output-heavy.

**C — don't do (trades quality):**
- Downgrading a COGNITION task (implement/review/architect/synthesize) to a cheaper model. The real savings are context + structure, not model-downgrade. When frontier is exhausted (maxed cap), **defer** — never finish cognition on a sub-frontier model.

**Never switch models inside one session** — invalidates the prompt cache, re-bills full history. "Switching" = the main brain delegating to fixed-model subagents.

## Phase 4 — Verify
Re-run `analyze_usage.py` after ~a week. Compare cost-equiv total, frontier %, subagent %, over-200K %. Confirm the quality bar held (spot-check outputs).

## Golden rules (durable)
1. Cognition → frontier (never downgrade). Retrieval → Haiku (zero loss). Judgment appears → frontier.
2. Context × turns × price is the bill; output ≈ 0. Attack context and structure, not model quality.
3. One session = one model = one job. `/clear` between jobs.
4. Weekly is cumulative + cost-weighted; 5-hour is a rolling rate. Fix fuel efficiency (frontier×parallel×long-nights), not burst speed.
5. Pin by ROLE, not version — aliases (`opus`/`fable`/`haiku`) auto-rotate to current models; update one FRONTIER list when a tier ships or a model goes unavailable.
