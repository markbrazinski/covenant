# Covenant — Record system (React + TypeScript port)

A React + TypeScript implementation of the locked **Record** visual system and **Layered
Causal Graph**.

## Where it lives / how to run

- Entry page: **`/index.html`** → `src/record/main.tsx`.
- Dev: `npm ci && npm run dev`, then open **`http://127.0.0.1:5173/analyze`**.
- Build: `npm run build` (`tsc --noEmit && vite build`).
- Recorded plans come from persisted, reconciled Gate 3 runs and survive reload.

## Routes (History API, route-driven product state)

| Route | Screen |
|---|---|
| `/analyze` | Upload a bounded Markdown/PDF agreement and start registry matching |
| `/analyze/:matchId` | Live match, extraction, and deterministic-verification progress |
| `/changes` | Reviewed data-use changes queue |
| `/changes/:changeId` | Reviewed change, rule deltas, explicit human activation |
| `/changes/:changeId/impact` | Analyzing → source resolve → graph population → Impact Plan → selection circuit → recording |
| `/impact-plans` | Persisted reconciled plans (newest first) |
| `/impact-plans/:planId` | Recorded plan: real targets, receipts, unresolved governance item, unaffected control, and originating change |

## Files (all under `src/record/`)

- `main.tsx` — entry, mounts `RecordApp`.
- `RecordApp.tsx` — routing + persistence orchestration; the ONE composition point
  (`GateApiDataSource` by default, `PreviewDataSource` only in explicit fixture mode);
  derives every view prop from `useCovenant` + route.
- `AppShell.tsx` — top nav (Changes / Impact Plans, no sidebar), breadcrumb, `ContextStrip`,
  live status + SR live region.
- `CausalGraph.tsx` — deterministic layered SVG graph. Layout from `TerminalPath.hops` only
  (never by entity name). Shared `ROW_Y` row-tracks align graph terminals to ledger rows.
- `ImpactLedger.tsx` — `ImpactTally`, `ImpactPlanRow`, `UnaffectedRow`, `EvidenceBundle`,
  `GovernanceHold`, `RecordingBanner`, `VerifiedReceipt`.
- `ImpactWorkspace.tsx` — two-pane presenter (graph + ledger); pure, no policy.
- `Changes.tsx` — `ChangesQueue`, `ReviewedChange` (activation).
- `Plans.tsx` — `PlansIndex`, `GovernanceBackBand`, `RecordedPlan`.
- `useHashRoute.ts` — tiny History API router + `usePrefersReducedMotion` (the filename
  is retained from the imported visual prototype).
- `dispositions.ts` — shape + label + colour, one place; receipt copy.
- `theme.css` — Record design tokens, scoped under `.record-root`.

## Adapted shared seam

The data/state/adapter seam remains visual-agnostic. The imported seam was adapted
to the real Gate 3 API while keeping fixture behavior isolated:

- `src/adapter/contracts.ts`, `src/adapter/DataSource.ts` — DTOs + `CovenantDataSource`.
- `src/adapter/PreviewDataSource.ts` — deterministic preview adapter (timers live here only).
- `src/state/useCovenant.ts`, `src/state/machine.ts` — state machine + hook.
- `src/data/viewModels.ts`, `src/data/canonical.ts` — DTO→VM mappers + canonical fixture.
- `src/types/domain.ts` — component-facing view models (honesty encoded in the types).

## The backend seam

`RecordApp.tsx` selects `GateApiDataSource` unless explicit fixture mode is configured. Progress
(`observeRun`/`observeRecording`), faults (`observeErrors`), evidence (`getEvidence`), and
receipts (`getReceipts`) all flow through the same interface. The Record view choreographs the
*returned* affected set into view by depth (`graphRevealTiers` / `graphRevealTerminals` from
`useCovenant`) — it is presentation animation, not fabricated streaming.

## Honesty invariants (enforced by reused types + this view)

- `Disposition` has no approved/executed/enforced/stopped member.
- Stop proposed renders **· not stopped**; governance review is **unresolved**, never given a
  proposed action; the unaffected control is never counted in the tally.
- Verified green appears only after a readback verifies; URNs / rule ids absent from the packet
  render **not exposed** — never fabricated.
- No affected terminals / paths / counts / tally before activation resolves the source.
- DataHub unavailable clears the affected set (no stale terminals, no cached plan as current).
- Partial write distinguishes recorded / verified / failed / pending; retry targets only
  incomplete records.

## Accessibility / motion

- Terminals and rows are real `<button>`s with `aria-pressed` + text-alternative labels; one
  `selectedTerminalId` binds path + intermediates + terminal + row + evidence; visible teal focus
  ring; polite live region announces analysis/recording. Disposition = shape + position + text.
- `prefers-reduced-motion` (or the dev Motion toggle) → step=0: immediate complete layout, no
  draw / stagger / focus sweep. Designed for 1440×900 at ~50% scale.

## Dev controls

Hidden unless explicit fixture mode and `?dev` are both present: replay, motion toggle,
and fixture fault injection. These controls never appear in real API mode.

## Verification note

The integrated port compiles under the strict `tsconfig.json`. The production build,
unit tests, dependency audit, and a real-browser run against the live Gate 3 API were
executed during Gate 5 verification; see the local Gate 5 integration report for exact
commands and results.
