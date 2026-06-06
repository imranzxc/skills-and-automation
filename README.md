# skills-and-automation

Skills and automation I use with Claude Code. Mostly things I got tired of doing by hand.

## skills

Every folder in `skills/` is one skill: a `SKILL.md` that Claude Code loads on its own. To use one, copy its folder into `~/.claude/skills/` (or symlink it).

### agent-council

A small panel of agents with different viewpoints argues a question out, then a judge gives back an answer. It keeps the disagreement visible instead of forcing a fake consensus, so you also see why they didn't fully agree. Useful when one model's first take isn't enough.

How it runs: everyone answers on their own, then reads the others and pushes back, then a judge settles on an answer plus the main points of disagreement and what would change the call.

### optimizing-spa-lighthouse-100

Getting a client-rendered SPA landing page to 100 across the board on Lighthouse. Not the obvious advice everyone already knows, but the gotchas that actually move the needle: variable-font axes eating your critical path, below-the-fold work blocking the first paint, heavy deps leaking into the entry bundle, a flaky background video on someone else's CDN. Written down after taking a real landing from mobile 64 to all-100.

## notes

Built for my own setup, so some paths and habits are specific to me. Take what's useful.
