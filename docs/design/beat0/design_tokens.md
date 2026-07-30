# Covenant Beat 0 — Design Tokens

Visual specification for the two-column (Variant B) extraction & verification workspace.
All values are taken verbatim from the design source. Build in the existing Covenant
codebase's patterns — these are references, not a framework.

## Color palette

| Semantic name | Hex | Usage |
|---|---|---|
| ink | `#181b1f` | Primary text; header bottom border (2px); ink button background |
| ink-2 (body strong) | `#3a3f45` | Receipt call line; captions on strong copy |
| text-2 | `#565a61` | Secondary body text, subtitles |
| muted | `#8b8e93` | Mono labels, helper text, receipt result line, "Done" tag |
| line | `#e1dfd8` | Card borders, dividers inside left column |
| line-2 | `#c8c5bc` | Outer workspace border, dashed slot border, PDF chip border |
| app background | `#d9d7cf` | Canvas behind the workspace |
| frame background | `#f5f4f0` | Workspace card fill |
| surface | `#ffffff` | Header bar, filled cards, receipt cards |
| surface-2 | `#faf9f6` | Empty document slot, PDF chip fill |
| activity panel bg | `#f0eee7` | Right "Agent activity" column (stone tone) |
| activity panel border | `#dcdad2` | Right column border + receipt card border |
| teal (structural) | `#1f6b73` | Primary action, links, "Select document" outline, Replace |
| verify (green) | `#1e7a4f` | Completed checkmarks, done dots — success ONLY |
| amber (processing) | `#a86a12` | Active/in-progress pulse dot + tag |
| warn (failure) | `#9c3524` | Failed dots, X marks, rejection/error text |

### Tint families (cards & pills)

| Tint | Background | Border | Heading text | Body text |
|---|---|---|---|---|
| green (verified / matched) | `#eef4ef` (matched card `#f2f7f3`) | `#a9d3bd` | `#0f5030` (matched `#5f8a71`) | `#2f6b4c` (matched `#5f8a71`) |
| warn (reject / error) | `#fbf3f1` | `#e3b9b0` | `#7a2a1d` | `#8a4034` |
| amber (no-match) | `#f8f0dd` | `#e6cf9c` | `#7a520c` | `#8a6414` |
| divider inside green card | — | `#cfe3d5` | — | — |

## Typography

Three families:
- **Source Serif 4** (`serif`) — display titles and product name only. Weights 600, 700.
- **Public Sans** — all product UI text. Weights 400, 500, 600, 700, 800.
- **IBM Plex Mono** (`mono`) — identifiers, filenames, hashes, dates, labels, tool-call receipts. Weights 400, 500, 600.

| Style | Family | Size / weight | Color | Notes |
|---|---|---|---|---|
| Product wordmark | Source Serif 4 | 18px / 600 | ink | Header left |
| Page title (h2) | Source Serif 4 | 23px / 700 | ink | letter-spacing -0.01em |
| Card heading (verified/reject/etc.) | Source Serif 4 | 19px / 700 | tint heading | 20px in some cards |
| Matched vendor name | Source Serif 4 | 20px / 700 | ink | |
| Body | Public Sans | 13px / 400 | text-2 | line-height 1.55 |
| Body strong / row label | Public Sans | 13px / 500–600 | ink | Phase row labels |
| Caption / helper | Public Sans | 12–12.5px / 400 | muted | |
| Section header (uppercase) | IBM Plex Mono | 10px / 600 | muted | letter-spacing 0.08em, text-transform uppercase |
| Mono label (field key) | IBM Plex Mono | 10px / 400–600 | muted | e.g. OBLIGATION, CANDIDATE ID |
| Mono value | IBM Plex Mono | 12.5–13px / 400–600 | ink / text-2 | e.g. ATLAS-LIC-004 |
| Mono receipt line | IBM Plex Mono | 11.5px / 400 | ink-2 (call) / muted (result) | line-height 1.65 |
| Status pill text | Public Sans | 11.5px / 600 | pill fg | |
| Status tag (phase) | Public Sans | 11px / 500–600 | muted / amber / warn | |
| Button | Public Sans | 14px / 600 | #fff | |

## Spacing

Consistent values seen across the design (px):

- Workspace outer padding: `30px 34px 36px`
- Header bar: height `56px`, padding `0 28px`, gap `24px`
- Two-column body gap: `26px`; right column fixed width `360px`; left column `flex:1.5`
- Card padding: `16–22px` (filled cards `14–16px`; success/reject cards `20–22px`)
- Section top margin: `18–24px`; section divider padding-top `14–16px`
- Grid/stack gap: `2px` (phase rows), `12px` (receipt cards), `6–10px` (small stacks)
- Field-group gaps: `22–34px` (summary fields), `9–10px` between label and value
- Icon-to-text gaps: `8–13px`

## Border radius

- All cards, buttons, pills, slots, PDF chip: **`2px`** (squared, restrained geometry).
- Status dots, checkmark badges, receipt dots: **`50%`** (circles).

## Status pill combinations

Format: `display:inline-flex; gap:7px; font:600 11.5px 'Public Sans'; padding:6px 12px; border-radius:2px`. Each has a leading glyph.

| Variant | Background | Border | Text | Glyph |
|---|---|---|---|---|
| neutral | `#eeece6` | `#d8d5cc` | `#565a61` | `○` |
| amber | `#f8f0dd` | `#e6cf9c` | `#8a5410` | `◐` |
| green | `#eef4ef` | `#a9d3bd` | `#0f5030` | `●` |
| warn | `#fbf3f1` | `#e3b9b0` | `#7a2a1d` | `✕` |

## Motion

- Single animation vocabulary: an amber "pulse" ring on the active phase dot and active receipt dot only.
  `@keyframes` expands `box-shadow: 0 0 0 0 rgba(168,106,18,.45)` → `0 0 0 6px rgba(168,106,18,0)`, 1.4s ease-out infinite.
- Honors `prefers-reduced-motion: reduce` (pulse disabled).
- No spinners, progress bars, percentages, or per-phase timers.

## Timing policy

No durations anywhere in the UI — completed checkmarks and the growing evidence trail carry
"real work happened." The **only** timing shown is the essential failure fact on the extraction-error
state: the phase tag `30.0s` and the receipt line `→ Timeout after 30s`.
