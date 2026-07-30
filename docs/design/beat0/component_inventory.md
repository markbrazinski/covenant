# Covenant Beat 0 — Component Inventory

Every reusable piece in the two-column (Variant B) workspace and the states it takes.
Colors/sizes reference `design_tokens.md`.

## Workspace shell
Outer card (`#f5f4f0`, 1px `#c8c5bc`, radius 2px) containing a fixed header and a two-column body.
- **Header bar**: white, 56px, 2px `#181b1f` bottom border. Left→right: serif wordmark "Covenant",
  mono breadcrumb "Analyses / New", flex spacer, status pill (right).
- **Body**: `display:flex; gap:26px`. Left column `flex:1.5` (~60%), right column fixed `360px`.

## Status pill (top-right)
One component, four variants — see token table. Leading glyph + label.
- **neutral** "Ready to analyze" — landing.
- **amber** "Matching agreement" / "Extracting via Bedrock" — in-progress.
- **green** "Candidate verified" — success.
- **warn** "Verification failed" / "Agreement not recognized" / "Extraction unavailable" — failures.

## Card (generic surface)
Squared 2px-radius bordered box, no shadow. Variants by tint family:
- **default** — white `#fff`, border `#e1dfd8` (document slot filled, receipt cards).
- **tinted-green** — `#eef4ef` / `#a9d3bd` (verified success card); matched-agreement uses the lighter `#f2f7f3`.
- **tinted-warn** — `#fbf3f1` / `#e3b9b0` (rejection card, error card).
- **tinted-amber** — `#f8f0dd` / `#e6cf9c` (no-match card).

## Phase row
`display:flex; align-items:center; gap:13px; padding:8px 4px`. Left: 15px state dot. Center: label
(flex:1). Right: small state tag (no timers). Rows stack with `gap:2px` under a mono uppercase header
("Matching to registered agreement" or "Extraction & verification").
- **pending** — hollow dot (1.5px `#c8c5bc` border, white fill), label muted, no tag.
- **active** — solid amber dot with pulse ring, label ink 600, tag "In progress" (amber).
- **complete** — solid green dot with white ✓, label ink 500, tag "Done" (muted).
- **failed** — solid warn dot with white ✕, label warn 600, tag "Failed" (or mono `30.0s` on the timeout row).

Phase label set (extraction): Preparing sources · Extracting via Bedrock · Verifying citations ·
Verifying schema · **Verifying rule types match cited language** · Candidate ready.
(Fallback if width breaks: "Verifying rule structure".)
Matching label set: Identifying vendor and obligation · Retrieving prior version from registry.

## Receipt card (Agent activity panel)
White card in the right column. Header row: 14px status dot + short label (flex:1) + state tag.
Below: two-line mono receipt — **call line** (ink-2, top) and **result line** (bottom).
- **active** — amber pulse dot, tag "Running", result line italic muted (`awaiting response…` / `awaiting completion…`).
- **complete** — green ✓ dot, tag "Done", result line muted (`→ Atlas Signals · v3 · effective 2024-08-01`, `→ 5 rules extracted · 5 citations verified`).
- **failed** — warn ✕ dot, tag "Failed", result line warn (`→ NOT_FOUND`, `→ Rejected · citation not found`, `→ Timeout after 30s`).

Labels in use: "Registry lookup", "Extraction & verification".

### Agent activity panel (container)
Right column: `#f0eee7` fill, 1px `#dcdad2` border, radius 2px, padding `18px 18px 20px`.
Mono uppercase header "Agent activity". Persistent across all frames; contents grow:
- **empty** — single muted line "No activity yet. Upload an agreement to begin." (no placeholder cards).
- **1 card** — lookup active (F2) / lookup NOT_FOUND (F6).
- **2 cards** — lookup done + extraction active/complete/failed (F3–F5, F7).

## Document slot
- **empty** — dashed `#c8c5bc` border, `#faf9f6` fill, centered: mono uppercase "Candidate version",
  teal-outlined "Select document" button, muted "or drop a PDF here".
- **filled** — white card. Top row: mono uppercase "Candidate version · uploaded" + teal "Replace".
  Body: PDF chip (36×44, `#faf9f6`, `#c8c5bc` border, amber "PDF") + filename (mono 600) + "418 KB · sha256: 3b7e10…" (mono muted).

## Matched-agreement card
Tinted-green (`#f2f7f3`). Top-right 20px green ✓ badge. Contents: mono uppercase "Matched to
governed agreement", serif "Atlas Signals", then two mono label/value pairs (OBLIGATION `ATLAS-LIC-004`,
IN-EFFECT PRIOR VERSION `v3 · effective 2024-08-01`). Appears (fades in) only after matching completes;
shown at 60% opacity while extraction runs, full opacity on terminal states.

## Button
- **primary teal** — `#1f6b73` fill, white 14/600, radius 2px, padding `12px 22px`. Used for
  "Continue to review" (verified).
- **primary ink** — `#181b1f` fill, same metrics. Used for recovery actions ("Try again",
  "Load a different document", "Retry extraction").
- **secondary link** — teal 12.5px/600 text, no box ("View extraction detail", "Register a new agreement").

## "↑ amends" connector
Centered mono glyph `↑ amends` in `#b3b1a9`, small vertical margin, between the uploaded document card
and the matched-agreement card. Signals that the candidate amends the retrieved prior version.

## Summary row (verified card)
Two mono label/value fields separated by `30px` gap: CANDIDATE ID `CANDIDATE-a3f2b1…`,
EXTRACTION MODEL `bedrock/claude-sonnet-4-5`. **No TOTAL ELAPSED field** (timing removed).

## Frame → state map
1. Landing (neutral, activity empty) · 2. Matching (amber, lookup active) ·
3. Extracting (amber, lookup done + extraction active, phase 5 active) · 4. Verified (green, both done) ·
5. Rejected (warn, extraction failed at citations) · 6. No match (warn, lookup NOT_FOUND, no extraction) ·
7. Extraction error (warn, Bedrock timeout).
