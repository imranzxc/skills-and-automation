---
name: cost-aware-runner
description: Use when starting a nightly/autonomous run, a research sprint, an audit campaign, or any multi-item batch — and whenever choosing which model to run a task on. Encodes the evidence-based cost-vs-quality routing (frontier on cognition, Haiku on retrieval), per-item context isolation, and anti-runaway. Triggers — "nightly run", "overnight", "audit campaign", "apply the backlog", "research sprint", "which model", "run this autonomously", "batch of tasks".
---

# Cost-aware runner

Durable routing + orchestration policy so work costs the least LIMIT without losing quality or volume.
Grounded in measured data: the `limit-optimizer` skill (a measured usage audit).

## The one rule: cognition vs retrieval

The token is **waste** if it re-processes junk or over-powers a mechanical task; it's **work** if it thinks on something that matters.

- **Retrieval → Haiku** (grep, read a file, navigate, `ls`, run a test/lint, triage-summary). A photocopier — a frontier model returns the *same bytes*. **Zero quality loss.**
- **Cognition → frontier, never downgrade** (implement, review, architect, plan, synthesize, judge, decision-summary): **Opus**; **Fable** for money/data-critical (billing/sync/auth/quota) and long-horizon/migration. `Sonnet` only for bounded mechanics with no judgment.
- The moment a "read" needs judgment ("read this code and find the security-relevant parts") it's cognition → frontier.

## Frontier rotation & fallback (durable)
- **Version bumps are automatic** — aliases (`opus`, `fable`, `haiku`) resolve to the current version. Opus 4.8→4.9 needs no change. Pin by ROLE, never by version.
- **A new top tier ships, or a tier goes unavailable** (maxed weekly cap — e.g. Fable often hits 100% first; export-control offline; disabled): update the **one** `FRONTIER` list at the top of `~/.claude/workflows/nightly-runner.js` (e.g. add a new model ahead of `fable`, or drop `fable`). Everything downstream follows.
- **Fallback = down the frontier, then DEFER — never down to sub-frontier.** Critical review tries `fable → opus`. If a cognition task's whole frontier chain is exhausted (all maxed), the runner **defers** the remaining work for the next run (resume after reset) — it does **not** silently finish it on Sonnet/Haiku. Quality is never traded for throughput.

## Never switch models inside one main session
It invalidates the prompt cache and re-bills the whole history at full rate. "Switching models" = the main brain (one model) **delegating to specialist subagents** (each a fixed model, its own context/cache), which report back a summary. The win of delegation is **context isolation**, not the cheaper model — so it works even with frontier subagents (verbose read → subagent → summary → main stays lean, killing the ~38% cache-write cost).

## Interactive discipline (automatic — no manual ritual)
- Window is capped at 200K (`CLAUDE_CODE_DISABLE_1M_CONTEXT=1`) and auto-compacts at ~70% (~140K). One session runs indefinitely; it compacts (your `PreCompact` hook checkpoints) instead of ballooning to 700K+. **Fewer manual sessions, not more** — before context rot, not after.
- Don't read big files into the main loop — delegate verbose reads to an `Explore`(Haiku) or Opus subagent that returns a summary.
- Rare genuine >200K single-task need: launch that one session with `CLAUDE_CODE_DISABLE_1M_CONTEXT=0 claude …`.

## Nightly / autonomous / batch → use the runner (never one long /loop)
A single long `/loop` balloons to ~950K over thousands of turns (expensive + rotted + fragile). Instead run **discrete tasks, each in its own fresh context** via the template:

```
Workflow({ scriptPath: '~/.claude/workflows/nightly-runner.js'  /* bundled beside this skill; copy it there */, args: {
  mode: 'tickets' | 'research-then-build' | 'audit' | 'fix' | 'research',
  question: '...',       // research / research-then-build: what to research
  ticketsPath: 'tickets.md',  // tickets mode: file to consume (default repo-root)
  workList: [...],       // optional explicit items; omit → scout discovers them
  critical: false,       // true → review on the top frontier (Fable) + sequential
  budgetStopK: 400,      // optional anti-runaway ceiling (K output tokens)
}})
```

**Modes** — nightly work varies, pick per night (or chain):
- `research-then-build` — **your usual flow**: phase 1 researches the question (Opus cognition, Haiku retrieval inside) and breaks it into Pocock vertical-slice tickets; phase 2 implements each ticket in its own fresh context → frontier review. One run, research → build.
- `tickets` — consume an existing `tickets.md` (from `/to-tickets`) and implement each in a fresh context, in dependency order. **This is Pocock's "work the frontier one ticket at a time, clearing context between tickets" — automated.**
- `audit` — Haiku scout finds defect areas → per-area audit (Opus) → verify.
- `fix` — Haiku scout lists backlog tasks → per-task implement (Opus) → review.
- `research` — sub-questions → per-question research (Opus) → verify.

**Compose with your Matt-Pocock skills — the runner drives YOUR method, not a generic one:**
- Full chain: `/to-spec` → `/to-tickets` (context-sized tickets, dependency order) → runner `tickets` mode → each ticket built via the `implement` skill (its own /tdd + typecheck + tests + `/code-review` + commit) in a fresh context.
- Build modes (`tickets`/`fix`/`research-then-build`) invoke **`implement`** on each item, so overnight builds are identical to your manual `/implement` per ticket — just with context auto-cleared between them. Since `implement` self-reviews via `/code-review`, the runner adds its own review pass **only for `critical:true`** (independent second look); otherwise no double-review.
- `prototype` (design questions), `triage` (incoming issues) slot in as before.

What it guarantees (see the template header for the why):
- **Per-item fresh context** → never balloons, 200K is plenty per item, no mid-run compaction / continuity loss.
- **Frontier on cognition** (do + review = Opus/Fable), **Haiku only on the scout/retrieval** → full quality where it matters.
- **Anti-runaway, not a work-cap**: processes the whole list by default; the optional ceiling and the 3-consecutive-no-progress guard only stop pathological loops, and unfinished items are **returned/logged for the next run — never silently dropped**.

Nightly work varies — pick `mode` per night (or run several): `audit` for sweeps, `fix` for backlog application, `research` for investigation. Same skeleton, right routing baked in.

## Don't (anti-patterns)
- ❌ Downgrade a *cognition* task to save limits — that trades quality; the real savings are context + structure.
- ❌ One giant overnight `/loop` session — use the runner.
- ❌ Frontier on pure retrieval (`cat`/grep on Fable) — that's frontier price for a photocopy.
- ❌ Switch models mid-session — delegate to a subagent instead.
