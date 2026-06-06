---
name: optimizing-spa-lighthouse-100
description: Use when a client-rendered SPA (Vite/React/TanStack Router on Cloudflare Pages or similar) landing page scores below 100 on Lighthouse / PageSpeed Insights — high LCP render delay, render-blocking requests, "reduce unused JavaScript", a heavy or flaky background asset, or failing color-contrast / robots.txt / console-error audits — and you need a repeatable path to 100 across Performance, Accessibility, Best Practices, and SEO.
---

# Optimizing a Client-Rendered SPA to Lighthouse 100

## Overview

**For a client-rendered SPA the LCP is gated by JavaScript execution (render delay), not the network.** TTFB is ~0; the Hero can't paint until the entry bundle downloads, parses, executes, and React renders the tree. So the wins are about **removing weight from the critical path** — in this order of impact: (1) fonts, (2) the synchronous render of below-the-fold sections, (3) heavy deps leaked into the shared entry, (4) heavy/flaky media. Then a11y/SEO/Best-Practices 100s are cheap static fixes.

Most agents already know the obvious moves (intersection-gate effects, robots.txt, aria-label, contrast, code-split, composite animations, CLS guards). **This skill is the non-obvious, empirically-proven gotchas that take a real SPA landing from mobile 64 → all-categories-100.**

## When to Use

- PSI/Lighthouse mobile Performance < 90, or any of A11y/BP/SEO < 100.
- Diagnostics show: **LCP render delay** (TTFB ~0, the LCP element is a Hero `<div>`/`<video>`), render-blocking requests, "Reduce unused JavaScript".
- A heavy/flaky background asset (esp. AI-generated video on a random 3rd-party CDN → `ERR_CONNECTION_FAILED`).
- Audit failures: `color-contrast`, `label-content-name-mismatch`, `robots.txt is not valid`, "browser errors logged to console".

Technology-specific: Vite + React + a file-based router, deployed as a static SPA (Cloudflare Pages / Netlify / similar). Adapt paths/config for your stack.

## The High-Impact Order (do these first)

### 1. Fonts are often the #1 critical-path item — drop unused variable-font axes

A self-hosted **variable font can be ~1MB** (.ttf), dwarfing your JS. Don't just convert to woff2 — **a variable font's `wdth`/`ital`/`slnt` axes are most of the gvar weight.** Check the `@font-face`: if it only declares `font-weight` (wght axis), the others are dead.

```bash
# venv with fonttools+brotli
python3 -m venv /tmp/fv && /tmp/fv/bin/pip install -q fonttools brotli
# inspect: which axes does the font have, which does CSS use?
/tmp/fv/bin/python -c "from fontTools.ttLib import TTFont;f=TTFont('Font-VF.ttf');print([a.axisTag for a in f['fvar'].axes])"
# pin the UNUSED axes (keep wght), then subset+woff2 (keep ALL glyphs + features = pixel-identical)
/tmp/fv/bin/python -m fontTools.varLib.instancer Font-VF.ttf ital=0 -o /tmp/inst.ttf   # drop ital only
/tmp/fv/bin/python -m fontTools.subset /tmp/inst.ttf --unicodes='*' --layout-features='*' --flavor=woff2 -o Font-VF.woff2
```

Result seen in practice: **965KB TTF → 178KB woff2 (drop ital axis), pixel-identical.** Update `@font-face` `src` + the `<link rel=preload>` to woff2; remove the TTF. **Verify identical** by measuring `getBoundingClientRect().width` of the same text at the same weights on old vs new — must match to 0.01px.

### 2. Lazy-load ALL below-the-fold sections (Hero stays eager)

The render delay is React rendering the **entire** component tree synchronously before first paint. Lazy-loading only the heavy *effects* isn't enough — the **section render itself** is the cost (dozens of sections, thousands of DOM nodes, on a 4×-throttled CPU).

```tsx
import { lazy, Suspense, type ReactNode } from 'react';
import { Hero } from './Hero'; // eager: above-fold + LCP element

const Manifesto = lazy(() => import('./Manifesto').then(m => ({ default: m.Manifesto })));
// ...one per below-fold section

function LazyBlock({ reserve, children }: { reserve: string; children: ReactNode }) {
  return <Suspense fallback={<div className={reserve} aria-hidden="true" />}>{children}</Suspense>;
}
// <Hero /> then <LazyBlock reserve="min-h-[140vh]"><Manifesto /></LazyBlock> ...
```

Initial render = Hero + light placeholders → paints immediately; section chunks load in parallel and render off-screen. **Empirically: LCP render delay 2420ms → 179ms.** This also code-splits each section's imports out of the entry (helps "unused JS" for free).

### 3. inView-gate standalone heavy decorative effects (WebGL/canvas/particles)

`React.lazy` alone does NOT defer a below-fold effect: the lazy boundary loads + mounts as soon as the **parent renders** (eager, even off-screen). Gate the *mount* on viewport intersection so WebGL init happens only near-viewport.

```tsx
export function useInView(ref, rootMargin = '300px') {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    if (typeof IntersectionObserver === 'undefined') { setInView(true); return; }
    const io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) { setInView(true); io.disconnect(); } }, { rootMargin });
    io.observe(el); return () => io.disconnect();
  }, [ref, rootMargin]);
  return inView; // latch: once true, stays true
}
// render the <Sparkles/> / <Globe/> / <VoiceOrb/> only when `inView`
```

(If you lazy the whole section per #2, effects inside are already deferred. inView is for effects that live in an *eager* container.)

### 4. Find heavy deps leaked into the SHARED entry chunk

**Root-layout always-mounted components leak their imports into the entry on EVERY page** — a `<Toaster>`, a search modal, hotkey handlers in `__root.tsx`. Classic: an always-mounted `<SearchModal />` statically imports the DB/repo layer → **dexie (~25KB) is in the entry of the guest landing** that has no search.

Fix: gate the always-mounted modal on its open-state + `React.lazy` it, so its deps load only on first open:

```tsx
const SearchModal = lazy(() => import('../components/search/SearchModal').then(m => ({ default: m.SearchModal })));
const searchOpen = useGlobalSearchOpen();           // lightweight store, no heavy deps
{searchOpen ? <Suspense fallback={null}><SearchModal /></Suspense> : null}
```

Result: **entry gzip 191KB → 156KB**, dexie out. Confirm with the bundle visualizer (`ANALYZE=1 pnpm build` → `dist/stats.html`). **`manualChunks` does NOT help** — a static import is loaded eagerly regardless of which chunk it's in; only dynamic `import()` (lazy) removes it from the entry's static graph.

### 5. Self-host + re-encode heavy/flaky media

A 3rd-party CDN background asset (esp. AI-gen video on a random `*.cloudfront.net`) intermittently fails → `ERR_CONNECTION_FAILED` in the console → **tanks Best Practices** (console-error audit) + is unreliable. Self-host in `public/` (same-origin) and re-encode:

```bash
# CRF (quality-based) not bitrate; KEEP native resolution; no audio; faststart for streaming
ffmpeg -i in.mp4 -c:v libx264 -crf 23 -preset slow -pix_fmt yuv420p -an -movflags +faststart public/hero-bg.mp4
```

Seen: **12.8Mbps / 15.3MB → CRF23 / 2.4MB at native 1080p**, near-original. **Do NOT downscale to 720p — it's visibly worse;** keep native resolution and let CRF do the work. Ensure a CSS gradient fallback so text never waits on the video. (Alternative: replace the video with a preloaded `<img>` poster as the LCP element — `fetchpriority=high` + intrinsic `width`/`height`.)

### 6. The cheap, decisive a11y / SEO / Best-Practices 100s

| Audit | Fix |
|---|---|
| `robots.txt is not valid (NNN errors)` | The SPA fallback serves `index.html` for `/robots.txt`. Add a **static** `public/robots.txt` (+ `sitemap.xml`, `llms.txt`). Static files are served before the SPA `/* → index.html` rewrite → `text/plain`. |
| `color-contrast` | Bump muted text to ≥4.5:1 (e.g. `text-zinc-500 → text-zinc-400` on a dark bg). Check the exact pair in DevTools color picker (shows AA badge), both themes. |
| `label-content-name-mismatch` (WCAG 2.5.3) | The button's accessible name must **contain** its visible text. `aria-label={`Выбрать модель: ${visibleName}`}` (or drop aria-label and let the text be the name). |
| console error → Best Practices | Usually the flaky media (#5). Otherwise read `mcp__chrome-devtools__list_console_messages` and fix at source. |
| render-blocking `registerSW.js` | vite-plugin-pwa: `injectRegister: 'script-defer'`. |

### 7. SPA indexability — private routes leak into the index with the homepage's meta

A client-rendered SPA serves the _same_ `index.html` (same `<title>`/meta) for **every** route, so Google can crawl a private route (`/admin`, `/settings`), get a 200 + the homepage title, index it — and sometimes rank it **above** the homepage for your brand. A clicked result then dumps the user on an auth wall / redirect.

- **`Disallow:` in robots.txt does NOT remove an already-indexed URL.** It only blocks crawling, so Google can never re-crawl to see a `noindex` → the URL stays **stuck** in results. This is the trap (we hit it with `/admin`).
- **Fix: `noindex`, not `Disallow`.** (1) Do **not** robots-`Disallow` the private SPA routes. (2) Serve `X-Robots-Tag: noindex` for them via host headers (Cloudflare Pages / Netlify `_headers`, e.g. `/admin` → `X-Robots-Tag: noindex`). Google crawls, sees `noindex`, drops them. (3) Keep robots `Disallow` only for non-HTML (`/api`). (4) Immediate removal of an already-stuck URL → Search Console **Removals** (no public API — manual).
- **Favicon: Google circle-crops it.** An edge-to-edge logo SVG looks cropped/oversized. Point `<link rel="icon">` at a **padded** icon (logo ~70% + solid bg), not the bare logomark.
- **Add JSON-LD** (`Organization` / `WebSite` / `SoftwareApplication`) to `index.html` — cheap entity signal + rich-result eligibility.
- **Bigger lever (separate effort): prerender the guest routes.** Even with perfect meta, a client-rendered body means Googlebot sees an empty `<div id="root">`; the static `<title>` is why it _has_ a title, but the content is JS-rendered → weak ranking for a new domain. Lighthouse won't flag this (it executes JS), but organic ranking suffers — SSG/prerender the public routes for the real win.

## CLS Safety — do not regress the Core Web Vital

- **Lazy sections: exact placeholder heights are impossible** (responsive, viewport-dependent). The real protection is **off-screen load**: small section chunks load in parallel right after the entry and render *while the user is still on the Hero* → shifts happen below the fold → CLS weight ≈ 0. Use a rough `min-h-[Nvh]` reserve just so the page isn't collapsed; **don't chase exact heights**. **Verify CLS = 0.00** after.
- inView effects in `absolute` / `aspect-square` / fixed-height containers → zero layout impact.
- Media: `width`/`height` attrs (img) or a fixed-size container reserve space.

## Verification — the gotchas that wasted hours

- **Verify on PROD (same-origin).** A local `vite preview` breaks a SPA landing if its `beforeLoad`/auth hook calls the API cross-origin → CORS → error boundary. Preview deploys (unique `*.pages.dev` hash) also CORS unless in `TRUSTED_ORIGINS`.
- **Fresh browser context per check** (chrome-devtools `new_page` `isolatedContext`). Reload restores scroll position → below-fold sections enter the viewport → inView effects mount → your "0 eager canvases" measurement is wrong.
- **Real input, not synthetic.** `dispatchEvent(new KeyboardEvent(...))` does NOT trigger hotkey handlers (untrusted event). Use CDP `mcp__chrome-devtools__press_key` (e.g. `Meta+k`).
- **The chrome-devtools performance trace is UNTHROTTLED (1× CPU)** → LCP looks great but won't reflect the throttled-mobile score. Good for CLS + render-delay *structure*; the real score is **Lighthouse/PSI mobile (4× CPU + slow 4G)**. Run both; trust PSI for the number.
- Hard-reload (Cmd+Shift+R) / incognito to dodge stale Service Worker cache.
- Confirm the LCP element (DevTools Performance → LCP marker). If it's the H1 text, the fix is preloading its font, not the bg asset.

## Common Mistakes

| Mistake | Reality |
|---|---|
| Subset the font but keep all axes | A variable font's `wdth`/`ital` axes are most of the weight. Drop unused axes (instancer) → 5-50× smaller, pixel-identical. |
| Only lazy the WebGL effects | React still renders every section synchronously → render delay. Lazy the whole below-fold section. |
| Fixed/exact placeholder heights for lazy sections | Impossible (responsive) and can *cause* CLS. Off-screen fast load is the protection. |
| `React.lazy` defers a below-fold effect | The lazy boundary mounts when the parent renders (eager). Gate on IntersectionObserver. |
| `manualChunks` to defer a dep | Static imports load eagerly regardless of chunk. Only dynamic `import()` lazifies. |
| Downscale video to 720p for size | Visibly worse. Keep native res, lower CRF. |
| Trust the unthrottled local trace as the score | 1× CPU. PSI mobile is 4× CPU + slow 4G. Run real Lighthouse-mobile. |
| Verify on localhost | API cross-origin → CORS → landing error boundary. Verify on prod, same-origin. |

## Workflow

1. Run **Lighthouse/PSI mobile** (the real score) + a **chrome-devtools performance trace** (LCP breakdown + CLS structure). Read the *specific* failing audits, don't guess.
2. Apply fixes in impact order: **fonts → lazy below-fold sections → entry dep-leak → media → quick a11y/SEO/BP**.
3. After EACH change: build, typecheck, tests, deploy to prod, **re-measure on a fresh isolated context** — confirm the target metric improved AND **CLS still 0**.
4. Final pass: PSI mobile + desktop. Target Perf 100 desktop / 90+ mobile, A11y/BP/SEO 100, CLS 0.

## Real-World Impact

One real Vite/React/TanStack-Router SPA landing on Cloudflare Pages, applying this skill end-to-end: mobile Performance **64 → 84+**, desktop **80 → 97**, Accessibility **97 → 100**, SEO **92 → 100**, Best Practices **96 → 100**, CLS **0** throughout. The remaining mobile gap (→90+) is the SPA render-delay itself — the proper fix beyond this skill is **prerendering/SSG the landing** (static HTML so the LCP content is in the markup, no client render delay).
