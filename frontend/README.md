# Covenant — Record (frontend)

React + TypeScript implementation of Covenant's bounded agreement-analysis,
review, layered causal graph, evidence, and native receipt experience. The real
Covenant API is the default.

```bash
cd frontend
cp .env.example .env
npm ci
npm run dev        # http://127.0.0.1:5173/analyze
npm run build      # tsc --noEmit && vite build
npm run test       # vitest (state machine, preview adapter, view models)
```

Full guide — routes, files, reused modules, the backend seam, honesty invariants, accessibility,
reduced motion, and dev controls (`?dev`) — is in **[`src/record/README.md`](./src/record/README.md)**.

## Structure

- `src/record/` — Analyze, review, impact, and recorded-plan views plus the History API routing shell.
- `src/adapter/` — `CovenantDataSource`, the real `GateApiDataSource`, and an explicit
  `PreviewDataSource` for isolated design tests.
- `src/state/` — state machine + `useCovenant` hook.
- `src/data/` — DTO→view-model mappers + the canonical sanitized fixture.
- `src/types/` — component-facing view models (product-honesty encoded in the types).

The one composition point is in `src/record/RecordApp.tsx`. Real HTTP is normal:

```ts
new GateApiDataSource({ baseUrl: import.meta.env.VITE_COVENANT_API_URL })
```

Fixture mode is opt-in only with `VITE_COVENANT_DATA_MODE=fixture`; API failures never
fall back to it.

Development uses a narrow cross-origin boundary: frontend
`http://localhost:5173` (or `http://127.0.0.1:5173`) to the configured loopback API.
The backend allows only those origins by default, configurable through
`COVENANT_CORS_ORIGINS`. Production should serve same-origin and set that variable
empty unless a specific trusted origin is required. History routes require the
static server to fall back to `index.html`.
