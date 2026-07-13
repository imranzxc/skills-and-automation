export const meta = {
  name: 'nightly-runner',
  description: 'Cost-aware nightly/research runner — per-item fresh context, frontier on cognition (with rotation/fallback) + Haiku on retrieval, anti-runaway',
  phases: [
    { title: 'Scout', detail: 'discover the work-list (Haiku retrieval, or Opus for research)' },
    { title: 'Execute', detail: 'per-item fresh context: do (frontier) -> review (frontier)' },
    { title: 'Report', detail: 'results + unfinished (never silently truncated)' },
  ],
}

// ── INVOKE ────────────────────────────────────────────────────────────
// Workflow({ scriptPath: '~/.claude/workflows/nightly-runner.js', args: {
//   mode: 'tickets' | 'research-then-build' | 'audit' | 'fix' | 'research',
//   question: '...',        // for research / research-then-build: what to research
//   ticketsPath: 'tickets.md',  // for tickets mode (default repo-root tickets.md)
//   workList: [...],        // optional explicit items (overrides scout)
//   scoutPrompt: '...',     // optional custom discovery
//   critical: false,        // money/data-critical -> review on the top frontier (Fable), sequential
//   budgetStopK: 400,       // optional anti-runaway ceiling (K OUTPUT tokens); defers remainder, never drops
// }})
//
// COMPOSES WITH your Matt-Pocock skills: run /to-tickets (research -> vertical-slice tickets, each
// sized for one fresh context, in dependency order) then this runner in `tickets` mode implements
// them one-per-fresh-context — automating Pocock's "work the frontier one ticket at a time, clearing
// context between tickets". `research-then-build` does both phases in one run.
//
// WHY (see the limit-optimizer skill): per-item fresh context => never balloons past 200K,
// no mid-run compaction/continuity loss; frontier on COGNITION, Haiku only on RETRIEVAL (zero quality
// loss); anti-runaway is a SAFETY net, not a volume cap.

// ── FRONTIER ROTATION (single source of truth) ────────────────────────
// Aliases auto-resolve to the CURRENT version (opus -> latest Opus), so version bumps need no change.
// Update this ONE list when a new top tier ships (e.g. add 'mythos' ahead of 'fable') or a tier is
// unavailable (maxed weekly cap / export-control / disabled). Order = highest -> next.
const FRONTIER = ['fable', 'opus']
const COGNITION = ['opus']            // default cognition floor; never drops below frontier
const RETRIEVAL = 'haiku'             // retrieval is a photocopier — cheapest, rarely capped

// try each tier in order; return first non-null. null => that whole chain is exhausted
// (maxed/offline). Callers DEFER on null — they never downgrade cognition to a sub-frontier model.
async function run(prompt, opts, chain) {
  for (const model of chain) {
    const r = await agent(prompt, { ...opts, model }).catch(() => null)
    if (r) return r
  }
  return null
}

const DO_SCHEMA = { type:'object', additionalProperties:false, required:['progress','summary'],
  properties:{ progress:{type:'string',enum:['done','partial','none']}, summary:{type:'string'},
    files:{type:'array',items:{type:'string'}}, details:{type:'string'} } }
const REVIEW_SCHEMA = { type:'object', additionalProperties:false, required:['verdict','mustFix'],
  properties:{ verdict:{type:'string',enum:['pass','fixes-needed','reject']},
    mustFix:{type:'array',items:{type:'string'}}, notes:{type:'string'} } }
const LIST_SCHEMA = { type:'object', additionalProperties:false, required:['items'],
  properties:{ items:{type:'array',items:{type:'string'}} } }

const A = args || {}
const MODE = A.mode || 'fix'
const CRIT = !!A.critical
const REVIEW_CHAIN = CRIT ? FRONTIER : COGNITION   // frontier review; Fable only for critical
const stopK = A.budgetStopK || null
const IS_RESEARCH = MODE === 'research' || MODE === 'research-then-build'
const BUILD = new Set(['tickets', 'fix', 'research-then-build'])   // modes that WRITE code
const isBuild = BUILD.has(MODE)
// build modes self-review + commit via Pocock `implement` (which runs /code-review internally),
// so the runner adds its own review ONLY for critical work (independent second pass). audit/research
// don't self-review -> always verify.
const needReview = CRIT || !isBuild
const VERB = ({ audit:'audit this area for real defects (correctness/security/regressions)',
  research:'research and analyze, grounding claims in sources' })[MODE] || 'complete this item'

// ── Scout: build the work-list ────────────────────────────────────────
// retrieval-scout (Haiku) for tickets/audit/fix; research-scout (Opus, COGNITION) for research modes.
phase('Scout')
let items = Array.isArray(A.workList) ? A.workList.slice() : null
if (!items) {
  const prompt = A.scoutPrompt || ({
    tickets: `Read ${A.ticketsPath || './tickets.md'} at the repo root. Return each ticket (## section) that is NOT fully checked-off, in file order (which is dependency order — blockers first). Retrieval only, do not implement. Output ONLY the JSON array of ticket titles+what-to-build strings.`,
    'research-then-build': `Research the question below, then break the result into Pocock tracer-bullet tickets: each a narrow COMPLETE vertical slice (schema→API→UI→tests), sized for ONE fresh context, in dependency order (blockers first). Output ONLY the JSON array of ticket strings (title + what-to-build). QUESTION: ${A.question || '(none given)'}`,
    research: `Break this research question into independent sub-questions, each answerable in its own fresh context. Output ONLY the JSON array. QUESTION: ${A.question || '(none given)'}`,
    audit: `Scan the repo and list discrete areas to audit for defects (each independently checkable). Retrieval/triage only. Output ONLY the JSON array.`,
    fix: `Scan the backlog/repo and list discrete, independently-actionable fix tasks. Retrieval/triage only. Output ONLY the JSON array.`,
  }[MODE] || `List discrete, independently-actionable items for a "${MODE}" run. Output ONLY the JSON array.`)
  const scout = await run(prompt,
    { label:'scout', phase:'Scout', effort: IS_RESEARCH ? 'high' : 'low', schema: LIST_SCHEMA },
    IS_RESEARCH ? COGNITION : [RETRIEVAL])
  items = (scout && scout.items) || []
}
log(`work-list: ${items.length} item(s)${stopK ? ` · ceiling ${stopK}K out` : ' · no ceiling (full list)'}`)
if (!items.length) return { mode: MODE, done: [], unfinished: [], note: 'empty work-list' }

// ── Execute: per-item, each its OWN fresh context ─────────────────────
phase('Execute')
const done = [], unfinished = []
let consecFail = 0, frontierGone = false

for (let i = 0; i < items.length; i++) {
  const item = items[i]
  if (stopK && budget.spent() / 1000 >= stopK) {
    for (let j = i; j < items.length; j++) unfinished.push(items[j])
    log(`ceiling ${stopK}K reached — ${unfinished.length} deferred to next run (NOT dropped)`); break
  }
  if (consecFail >= 3) {
    for (let j = i; j < items.length; j++) unfinished.push(items[j])
    log(`3 consecutive no-progress — runaway guard halt; ${unfinished.length} deferred`); break
  }

  // stage 1 — DO (COGNITION -> frontier). Fresh isolated context per item.
  const doPrompt = isBuild
    ? `Ticket (${MODE}): ${item}\n\nUse the \`implement\` skill to build this: /tdd at sensible seams, run typecheck + single test files throughout and the full suite once at the end, then /code-review, then commit to the current branch. If the skill can't be loaded, follow that exact method. FRESH clean context — read ONLY what THIS ticket needs (targeted reads/grep, never dump whole files). Then report.`
    : `Item (${MODE}): ${item}\n\n${VERB}. FRESH clean context — read ONLY what THIS item needs (targeted reads/grep, never dump whole files). Do the work, then report.`
  const work = await run(doPrompt, { label:`do:${i}`, phase:'Execute', schema: DO_SCHEMA }, COGNITION)

  if (work === null) {   // frontier exhausted (Opus maxed/unavailable) — DEFER, never downgrade
    for (let j = i; j < items.length; j++) unfinished.push(items[j])
    frontierGone = true
    log(`frontier exhausted at item ${i} — deferring ${unfinished.length}, resume when limits reset`); break
  }
  if (work.progress === 'none') { consecFail++; unfinished.push(item); continue }
  consecFail = 0

  // stage 2 — REVIEW (COGNITION -> frontier; Fable if critical). Own fresh context.
  // Build modes already self-reviewed via implement's /code-review, so this runs only when
  // critical (independent second pass). audit/research always verify.
  let review = null
  if (needReview) {
    const revPrompt = isBuild
      ? `Independently review the just-committed changes for ticket "${item}" — use the \`code-review\` skill (Standards + Spec axes) and adversarially verify no regressions/blind casts. This is a critical second pass on top of the implement-time review.\n\nWHAT WAS DONE:\n${JSON.stringify(work).slice(0,6000)}`
      : `Adversarially review this ${MODE} result for "${item}". Default to skepticism; surface real defects (correctness, regressions, missed edges, blind casts).\n\nRESULT:\n${JSON.stringify(work).slice(0,6000)}`
    review = await run(revPrompt, { label:`review:${i}`, phase:'Execute', effort:'high', schema: REVIEW_SCHEMA }, REVIEW_CHAIN)
  }

  done.push({ item, progress: work.progress, summary: work.summary, files: work.files || [], review })
}

phase('Report')
return { mode: MODE, critical: CRIT, frontierExhausted: frontierGone, done, unfinished,
  summary: `${done.length} completed, ${unfinished.length} deferred${frontierGone ? ' (frontier exhausted — resume after reset)' : ''}`,
  needsFix: done.filter(d => d.review && d.review.verdict !== 'pass').map(d => ({ item: d.item, mustFix: d.review.mustFix })) }
