#!/usr/bin/env python3
"""Claude Code limit diagnostic — parses local transcripts (ccusage-style dedup) into a
readable report: where the weekly limit actually goes. Portable, no user-specific paths.

Usage:  python3 analyze_usage.py [tz_offset_hours]
  tz_offset_hours: optional local-time offset from UTC for the by-hour/night view (default 0).

Cost figures are an API-$-equivalent PROXY for limit weight (the Max weekly cap is cost-weighted).
Prices below are per-MTok, VERIFIED 2026-07-13 — re-verify at platform.claude.com/docs/en/about-claude/pricing.
"""
import json, os, sys
from collections import defaultdict

TZ = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ROOT = os.path.expanduser("~/.claude/projects")

# per-MTok: input / output / cache-read / cache-write(1h). Update when prices change.
PRICE = {
    "fable":  {"in":10.0, "out":50.0, "cr":1.00, "cw":20.0},
    "opus":   {"in":5.0,  "out":25.0, "cr":0.50, "cw":10.0},
    "sonnet": {"in":3.0,  "out":15.0, "cr":0.30, "cw":6.0},
    "haiku":  {"in":1.0,  "out":5.0,  "cr":0.10, "cw":2.0},
}
def tier(m):
    m = (m or "").lower()
    for t in ("opus", "sonnet", "haiku", "fable"):
        if t in m: return t
    return None
def cost(t, u):
    p = PRICE.get(t)
    if not p: return 0.0
    return ((u.get("input_tokens",0) or 0)/1e6*p["in"] + (u.get("output_tokens",0) or 0)/1e6*p["out"]
            + (u.get("cache_read_input_tokens",0) or 0)/1e6*p["cr"]
            + (u.get("cache_creation_input_tokens",0) or 0)/1e6*p["cw"])

files = []
for dp, dn, fn in os.walk(ROOT):
    for f in fn:
        if f.endswith(".jsonl"): files.append(os.path.join(dp, f))

seen = set(); dup = 0
by_model = defaultdict(lambda: defaultdict(float))
by_chain = defaultdict(lambda: defaultdict(float))
by_chain_tier = defaultdict(lambda: defaultdict(float))
by_day = defaultdict(float); by_hour = defaultdict(float)
sess = defaultdict(lambda: {"cost":0.0,"turns":0,"maxctx":0,"start":None})
tools = defaultdict(int); mcp = defaultdict(int); skills = defaultdict(int); agents = defaultdict(int)
ctx_buckets = defaultdict(int)
tt = {"cr":0.0,"cw":0.0,"in":0.0,"out":0.0}; turns = 0

def bucket(n):
    for lim,name in [(50e3,"0-50K"),(100e3,"50-100K"),(150e3,"100-150K"),(200e3,"150-200K"),
                     (300e3,"200-300K"),(500e3,"300-500K")]:
        if n < lim: return name
    return "500K+"

for fp in files:
    side = "subagent" if "/subagents/" in fp else "main"
    try: f = open(fp)
    except Exception: continue
    for line in f:
        has_use = '"tool_use"' in line
        if '"usage"' not in line and not has_use: continue
        try: o = json.loads(line)
        except Exception: continue
        if o.get("type") != "assistant": continue
        msg = o.get("message") or {}; mid = msg.get("id")
        if mid and mid in seen and not has_use: dup += 1; continue
        u = msg.get("usage") or {}
        # tool_use accounting (dedup separately is fine; count once per message id)
        if has_use and (not mid or mid not in seen):
            for blk in (msg.get("content") or []):
                if isinstance(blk, dict) and blk.get("type") == "tool_use":
                    nm = blk.get("name") or "?"; tools[nm]+=1
                    if nm.startswith("mcp__"): mcp[nm.split("__")[1] if len(nm.split("__"))>1 else nm]+=1
                    inp = blk.get("input") or {}
                    if nm == "Skill" and isinstance(inp,dict): skills[inp.get("skill") or inp.get("command") or "?"]+=1
                    if nm in ("Task","Agent") and isinstance(inp,dict): agents[inp.get("subagent_type") or "?"]+=1
        if mid:
            if mid in seen: continue
            seen.add(mid)
        if not u: continue
        model = msg.get("model") or "unknown"; t = tier(model)
        c = cost(t, u)
        inp=u.get("input_tokens",0)or 0; out=u.get("output_tokens",0)or 0
        cr=u.get("cache_read_input_tokens",0)or 0; cw=u.get("cache_creation_input_tokens",0)or 0
        ctx = inp+cr+cw; total = ctx+out
        turns += 1
        bm=by_model[model]; bm["cost"]+=c; bm["tok"]+=total
        by_chain[side]["cost"]+=c; by_chain_tier[side][t or "?"]+=c
        tt["cr"]+=cr; tt["cw"]+=cw; tt["in"]+=inp; tt["out"]+=out
        ts=o.get("timestamp","")
        if ts[:10]: by_day[ts[:10]]+=c
        try: by_hour[(int(ts[11:13])+TZ)%24]+=c
        except Exception: pass
        if ctx>0: ctx_buckets[bucket(ctx)]+=1
        sid=o.get("sessionId") or "?"; s=sess[sid]
        s["cost"]+=c; s["turns"]+=1; s["maxctx"]=max(s["maxctx"],ctx)
        if s["start"] is None or ts<s["start"]: s["start"]=ts
    f.close()

def h(n): return f"{n/1e9:.1f}B" if n>=1e9 else (f"{n/1e6:.0f}M" if n>=1e6 else f"{n/1e3:.0f}K")
tot = sum(v["cost"] for v in by_model.values()) or 1
P = print
P("="*64); P("  CLAUDE CODE LIMIT DIAGNOSTIC"); P("="*64)
P(f"files={len(files)}  unique_turns={turns}  dedup_skipped={dup}")
P(f"cost-equiv total (limit-weight proxy): ${tot:,.0f}   [tz offset {TZ:+d}h for hours]")

P("\n--- BURN BY MODEL ---")
for m,v in sorted(by_model.items(), key=lambda kv:-kv[1]["cost"]):
    if v["cost"]<0.5: continue
    P(f"  {m:26s} ${v['cost']:8,.0f} ({100*v['cost']/tot:4.1f}%)  {h(v['tok'])}")
front = sum(v["cost"] for m,v in by_model.items() if tier(m) in ("opus","fable"))
P(f"  >>> frontier-tier (opus+fable): {100*front/tot:.0f}% of burn")

P("\n--- TOKEN-TYPE SPLIT (context-bloat tell) ---")
g = sum(tt.values()) or 1
for k,lbl in [("cr","cache_read"),("cw","cache_write"),("in","fresh_input"),("out","output")]:
    P(f"  {lbl:12s} {h(tt[k]):>7s}  {100*tt[k]/g:5.1f}%")

P("\n--- MAIN vs SUBAGENT ---")
for side,v in sorted(by_chain.items(), key=lambda kv:-kv[1]["cost"]):
    mm=by_chain_tier[side]; s=sum(mm.values()) or 1
    mix=" ".join(f"{k}={100*vv/s:.0f}%" for k,vv in sorted(mm.items(),key=lambda x:-x[1]) if vv>1)
    P(f"  {side:9s} ${v['cost']:8,.0f} ({100*v['cost']/tot:3.0f}%) | {mix}")

P("\n--- CONTEXT SIZE PER TURN ---")
order=["0-50K","50-100K","100-150K","150-200K","200-300K","300-500K","500K+"]
tb=sum(ctx_buckets.values()) or 1
for b in order:
    n=ctx_buckets.get(b,0); P(f"  {b:9s} {n:7d}  {100*n/tb:4.1f}%  {'#'*int(40*n/tb)}")
over=sum(ctx_buckets.get(b,0) for b in ["200-300K","300-500K","500K+"])
P(f"  >>> turns OVER 200K: {100*over/tb:.0f}%")

P("\n--- CACHE ECONOMICS (limit-weight at opus rates) ---")
P(f"  cache_read  ${tt['cr']/1e6*0.5:8,.0f}   cache_write ${tt['cw']/1e6*10:8,.0f} (2x rate!)   cold_input ${tt['in']/1e6*5:8,.0f}")

P("\n--- BY HOUR (local) — night vs day ---")
night=sum(by_hour[x] for x in range(0,8)); day=sum(by_hour.values())-night
P(f"  night(00-08)=${night:,.0f} ({100*night/(night+day+1):.0f}%)   day=${day:,.0f}")
mx=max(by_hour.values()) if by_hour else 1
for x in range(24):
    c=by_hour.get(x,0); tag="night" if 0<=x<8 else "     "
    P(f"  {tag} {x:02d}h ${c:6,.0f} {'#'*int(30*c/(mx or 1))}")

P("\n--- TOP WHALE SESSIONS (likely overnight balloons) ---")
for k,v in sorted(sess.items(), key=lambda kv:-kv[1]["cost"])[:10]:
    st=(v["start"] or "?")[:16].replace("T"," ")
    P(f"  ${v['cost']:6,.0f}  {v['turns']:5d} turns  maxctx={v['maxctx']//1000:4d}K  start={st}Z")

P("\n--- ACTUAL USAGE (prune what's never used) ---")
P("  MCP servers: " + ", ".join(f"{k}({n})" for k,n in sorted(mcp.items(),key=lambda x:-x[1])[:15]))
P("  Agents used: " + ", ".join(f"{k}({n})" for k,n in sorted(agents.items(),key=lambda x:-x[1])[:10]))
P("  Skills used: " + ", ".join(f"{k}({n})" for k,n in sorted(skills.items(),key=lambda x:-x[1])[:12]))

P("\n--- AUTO-FLAGGED SIGNALS ---")
if tt["cr"]/g > 0.9: P("  ⚠ cache_read >90% → context×turns dominates. Cap window, /clear, delegate reads, trim always-loaded docs/plugins/memory.")
if 100*front/tot > 80: P("  ⚠ frontier >80% of burn → route RETRIEVAL to Haiku (0 quality loss); keep frontier only on cognition.")
sub=by_chain.get("subagent",{}).get("cost",0)
if sub/tot > 0.2:
    st=by_chain_tier.get("subagent",{}); fr=sum(v for k,v in st.items() if k in ("opus","fable"))/(sum(st.values()) or 1)
    P(f"  ⚠ subagents {100*sub/tot:.0f}% of burn, {100*fr:.0f}% frontier → pin workflow/Task workers by role (retrieval→Haiku).")
if 100*over/tb > 30: P(f"  ⚠ {100*over/tb:.0f}% of turns >200K → ballooning sessions. Cap window to 200K; run overnight as discrete tasks, not one /loop.")
if 100*night/(night+day+1) > 30: P(f"  ⚠ {100*night/(night+day+1):.0f}% burn at night → overnight autonomous runs are a top driver. Discrete-task runner + anti-runaway.")
P("="*64)
