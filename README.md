# skills-and-automation

Skills and automation I use with Claude Code. Mostly things I got tired of doing by hand.

## skills

Every folder in `skills/` is one skill: a `SKILL.md` that Claude Code loads on its own. To use one, copy its folder into `~/.claude/skills/` (or symlink it).

### agent-council

A small panel of agents with different viewpoints argues a question out, then a judge gives back an answer. It keeps the disagreement visible instead of forcing a fake consensus, so you also see why they didn't fully agree. Useful when one model's first take isn't enough.

How it runs: everyone answers on their own, then reads the others and pushes back, then a judge settles on an answer plus the main points of disagreement and what would change the call.

### optimizing-spa-lighthouse-100

Getting a client-rendered SPA landing page to 100 across the board on Lighthouse. Not the obvious advice everyone already knows, but the gotchas that actually move the needle: variable-font axes eating your critical path, below-the-fold work blocking the first paint, heavy deps leaking into the entry bundle, a flaky background video on someone else's CDN. Written down after taking a real landing from mobile 64 to all-100.

### limit-optimizer

Figures out why you're burning through your Claude Code usage limits so fast, then fixes it — from your **real data**, not guesses. It parses your local transcripts (ccusage-style dedup) into a report of where the weekly limit actually goes: burn by model, the cache-read/context split, main-vs-subagent, context-size distribution, night-vs-day, the biggest "whale" sessions, and which MCP servers/skills you never actually use — with auto-flagged signals. Then it pairs that with your `/context`, `/usage`, and `/doctor` output and applies evidence-based optimizations under one rule: **cut waste, never work**. Includes the limit mechanics most people get wrong (weekly is a cumulative cost-weighted total, 5-hour is a rolling rate; fast mode never touches the weekly cap). Run `scripts/analyze_usage.py` to see your own numbers.

### cost-aware-runner

The ongoing execution policy that pairs with limit-optimizer. One rule for which model runs what: **frontier (Opus/Fable) on cognition, Haiku on retrieval** — a photocopier task (grep, read a file) gets the same bytes from Haiku, so paying frontier for it is pure waste, while anything with judgment stays frontier. It also encodes context discipline (never let a session balloon; delegate verbose reads to a subagent so the main loop stays lean) and a bundled `nightly-runner.js` workflow for overnight/batch work: each item runs in its own fresh context (no ballooning, no mid-run compaction), frontier-with-fallback routing (`fable → opus`, and if the whole frontier is exhausted it *defers* rather than downgrading), and an anti-runaway guard that never silently drops work. Composes with the Matt-Pocock `to-tickets` / `implement` skills. Copy `nightly-runner.js` into `~/.claude/workflows/`.

## notes

Built for my own setup, so some paths and habits are specific to me. Take what's useful.
