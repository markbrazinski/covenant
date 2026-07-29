# Covenant — Record (frontend)

React + TypeScript implementation of the locked **Record** visual system and **Layered Causal
Graph**, integrated with the real Covenant Gate 3 API by default.

```bash
cd frontend
npm install
cp .env.example .env
npm run dev        # http://localhost:5173/changes
npm run build      # tsc --noEmit && vite build
npm run test       # vitest (state machine, preview adapter, view models)
```

Full guide — routes, files, reused modules, the backend seam, honesty invariants, accessibility,
reduced motion, and dev controls (`?dev`) — is in **[`src/record/README.md`](./src/record/README.md)**.

## Structure

- `src/record/` — the Record view + History API routing shell (the app).
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
