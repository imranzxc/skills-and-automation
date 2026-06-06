# skills-and-automation

Skills and automation I use with Claude Code. Mostly things I got tired of doing by hand.

## skills

Every folder in `skills/` is one skill: a `SKILL.md` that Claude Code loads on its own. To use one, copy its folder into `~/.claude/skills/` (or symlink it).

### agent-council

A small panel of agents with different viewpoints argues a question out, then a judge gives back an answer. It keeps the disagreement visible instead of forcing a fake consensus, so you also see why they didn't fully agree. Useful when one model's first take isn't enough.

How it runs: everyone answers on their own, then reads the others and pushes back, then a judge settles on an answer plus the main points of disagreement and what would change the call.

## notes

Built for my own setup, so some paths and habits are specific to me. Take what's useful.
