---
name: agent-council
description: Use when a question or decision benefits from multiple agents debating to a reasoned answer — high-stakes/ambiguous choices, architecture trade-offs, "is this actually true?", surfacing blind spots. Spawns a diverse panel that proposes, argues/rebuts across rounds, then a judge converges to a conclusion with confidence, consensus, dissent and cruxes. The peer-debate this environment lacks natively (it's hub-and-spoke), simulated deterministically via Workflow.
---

# Agent Council — debate to truth

Multi-agent deliberation: a diverse panel **proposes** independent positions, **argues** (each critiques the others and revises across rounds), then a **judge** converges to a reasoned conclusion — with honest dissent and the crux of any remaining disagreement.

This is the "agents communicate, argue, arrive at truth" pattern. This environment is hub-and-spoke (no native peer-to-peer agent messaging), so the debate is orchestrated deterministically via the `Workflow` tool: between rounds, every panelist is fed the full transcript of the others, which reproduces real cross-examination.

## When to use

- High-stakes or ambiguous decisions (architecture, product sequencing, "build X or Y first").
- "Is this claim actually true / is this approach sound?" — adversarial pressure-test.
- Surfacing blind spots: one model answering alone has one frame; a diverse panel has several.
- Design trade-offs where the *cruxes* matter as much as the answer.

## When NOT to use

- Simple factual lookups or mechanical tasks (use a single agent / direct answer).
- When you already know the answer — debate burns tokens for no gain.
- Time-critical trivial choices.

## How to run

When invoked (`/agent-council <question>` or "созови совет по …"), run the Workflow below via the `Workflow` tool, passing the question through `args`. Do **not** rewrite the script per question — only change `args`:

```
Workflow({ script: <the script below>, args: { question: "<user question>", rounds: 1, panelists: 4 } })
```

`args` fields:
- `question` (required) — the question/decision to deliberate.
- `rounds` (default 1) — number of debate/rebuttal rounds (2 for thorny/contested topics).
- `panelists` (default 4) — ignored if `roles` given.
- `roles` (optional) — array of persona strings to override the default diverse lenses.

After it completes: relay the judge's verdict (answer + confidence + consensus + dissent + crux + what-would-change-it). The full positions are in the return value if the user wants the trail. Scale up (`rounds: 2`, more roles) for "thoroughly debate this".

## The workflow script

```javascript
export const meta = {
  name: 'agent-council',
  description: 'Diverse panel proposes, debates/rebuts across rounds, judge converges to a reasoned answer',
  phases: [
    { title: 'Propose', detail: 'panelists answer independently' },
    { title: 'Debate', detail: 'each critiques others and revises (peer cross-examination)' },
    { title: 'Adjudicate', detail: 'judge converges to conclusion + dissent + crux' },
  ],
}

// args may arrive as an object, a JSON string, or a plain question string.
let A = args
if (typeof A === 'string') {
  const t = A.trim()
  if (t.startsWith('{')) {
    try {
      A = JSON.parse(t)
    } catch {
      A = { question: A }
    }
  } else {
    A = { question: A }
  }
}
const question = A?.question
if (!question) throw new Error('agent-council: pass args.question (string or {question})')
const ROUNDS = A?.rounds || 1
const ROLES =
  (Array.isArray(A?.roles) && A.roles) || [
    'Прагматик — что реально сработает с минимумом риска и усилий; bias к простоте и доставке.',
    'Архитектор/пурист — корректность, долгосрочное здоровье системы, правильные абстракции; bias к «сделать правильно».',
    'Скептик / red-team — где это сломается, скрытые издержки, контрпримеры; задача атаковать слабые места любой позиции.',
    'Доменный эксперт — специфика именно этой задачи, edge cases, что знают практики; bias к реальности предметной области.',
  ]

const POSITION_SCHEMA = {
  type: 'object',
  properties: {
    position: { type: 'string' },
    reasoning: { type: 'array', items: { type: 'string' } },
    keyAssumptions: { type: 'array', items: { type: 'string' } },
    confidence: { type: 'number' },
  },
  required: ['position', 'reasoning', 'confidence'],
}
const CRITIQUE_SCHEMA = {
  type: 'object',
  properties: {
    critiquesOfOthers: {
      type: 'array',
      items: {
        type: 'object',
        properties: { who: { type: 'string' }, strongestObjection: { type: 'string' } },
        required: ['who', 'strongestObjection'],
      },
    },
    conceded: { type: 'array', items: { type: 'string' } },
    revisedPosition: { type: 'string' },
    confidence: { type: 'number' },
  },
  required: ['revisedPosition', 'confidence'],
}
const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    answer: { type: 'string' },
    confidence: { type: 'number' },
    consensus: { type: 'array', items: { type: 'string' } },
    disagreements: { type: 'array', items: { type: 'string' } },
    crux: { type: 'string' },
    whatWouldChangeIt: { type: 'string' },
    dissentingView: { type: 'string' },
    converged: { type: 'boolean' },
  },
  required: ['answer', 'confidence', 'crux'],
}

function proposePrompt(role) {
  return [
    'Ты — участник совета экспертов, который дебатирует к истине. Твоя ЛИНЗА:',
    role,
    'ВОПРОС:',
    question,
    'Дай свою независимую позицию ЧЕРЕЗ свою линзу. Не пытайся быть нейтральным — займи позицию и обоснуй. Отвечай на языке вопроса. Конкретно, без воды. Верни position, reasoning (буллеты), keyAssumptions, confidence (0-1).',
  ].join('\n\n')
}

function transcriptText(items) {
  return items
    .map((p, i) => `### Участник ${i + 1} (${p.role})\nПозиция: ${p.position || p.revisedPosition}\nДоводы: ${(p.reasoning || []).join('; ')}`)
    .join('\n\n')
}

function debatePrompt(role, transcript, roundIdx) {
  return [
    'Ты — участник совета. Твоя линза: ' + role,
    'ВОПРОС: ' + question,
    'Раунд дебатов #' + (roundIdx + 1) + '. Позиции участников на данный момент:',
    transcriptText(transcript),
    'Задача: (1) для каждого другого участника сформулируй СИЛЬНЕЙШЕЕ возражение (steelman оппонента, потом атакуй); (2) честно признай в чём другие правы (conceded); (3) пересмотри свою позицию с учётом услышанного (revisedPosition) — двигайся к истине, а не упрямься. Если другой убедил — меняй мнение. Верни critiquesOfOthers, conceded, revisedPosition, confidence.',
  ].join('\n\n')
}

function judgePrompt(initial, finalRound) {
  return [
    'Ты — председатель совета (беспристрастный судья, НЕ участник). Сведи дебаты к обоснованному выводу.',
    'ВОПРОС: ' + question,
    'Изначальные позиции:',
    transcriptText(initial),
    'Финальные (после дебатов) позиции:',
    transcriptText(finalRound),
    'Определи: answer (обоснованный вывод — «истина» к которой пришли, не форсируй ложный консенсус), confidence (0-1), consensus (в чём согласны), disagreements (где разошлись), crux (главный узел разногласия — от чего зависит ответ), whatWouldChangeIt (какой факт/условие изменили бы вывод), dissentingView (сильнейшая несогласная позиция, чтобы не потерять), converged (bool — пришли ли к согласию). Отвечай на языке вопроса.',
  ].join('\n\n')
}

phase('Propose')
log('Совет из ' + ROLES.length + ' участников, ' + ROUNDS + ' раунд(ов) дебатов')
const initial = (
  await parallel(
    ROLES.map((role) => () =>
      agent(proposePrompt(role), { schema: POSITION_SCHEMA, label: 'propose', phase: 'Propose', model: 'sonnet' }).then((p) =>
        p ? { role, ...p } : null
      )
    )
  )
).filter(Boolean)

phase('Debate')
let transcript = initial
for (let r = 0; r < ROUNDS; r++) {
  const round = (
    await parallel(
      transcript.map((p) => () =>
        agent(debatePrompt(p.role, transcript, r), { schema: CRITIQUE_SCHEMA, label: 'debate:r' + (r + 1), phase: 'Debate', model: 'sonnet' }).then((c) =>
          c ? { role: p.role, position: c.revisedPosition, reasoning: [c.revisedPosition], ...c } : null
        )
      )
    )
  ).filter(Boolean)
  if (round.length) transcript = round
}

phase('Adjudicate')
const verdict = await agent(judgePrompt(initial, transcript), { schema: VERDICT_SCHEMA, label: 'judge', phase: 'Adjudicate', model: 'opus' })
return { question, verdict, finalPositions: transcript }
```

## Notes / tuning

- **Diversity is the engine.** Default roles are distinct lenses (pragmatist / architect / red-team / domain-expert), not N clones — diversity surfaces more than redundancy. Override `roles` for domain-specific panels (e.g. security / perf / UX / cost).
- **Honest convergence.** The judge is instructed NOT to force consensus — if there's a real crux, it's surfaced (`converged:false` + `crux`). That's a feature: knowing *why* smart agents disagree is often the real value.
- **Cost.** ~`panelists × (1 + rounds) + 1` agents (default 4 → 9). Use `rounds:2` only for genuinely contested topics.
- **Models.** Panelists on sonnet (debate volume), judge on opus (synthesis quality).
- **Reusable by name** (optional): the same script can be saved to `.claude/workflows/agent-council.js` and invoked via `Workflow({ name: 'agent-council', args })`.
