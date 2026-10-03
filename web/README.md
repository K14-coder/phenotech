# Rare Disease Atlas: web

Front end for Hack-Nation Challenge 05. It reads `public/data/graph.json`, which follows `../docs/SCHEMA.md`.

```bash
npm install
npm run dev     # http://127.0.0.1:3000  (syncs ../data/graph.json first, if present)
npm run build
```

- Views: `/` (search), `/atlas?focus=<id>`, `/disease/<GENE>`, `/path?from=<id>&to=<id>`.
- Every connection opens an Evidence panel with sources, verbatim quotes, confidence, and contradicting evidence.
- `lib/ai.ts` exposes `generate(kind, payload)`. Today it serves precomputed files from `public/data/ai/`, otherwise it reports "AI not connected".
- The bundled `graph.json` is SAMPLE data (`meta.sample: true`, placeholder evidence). Regenerate it with `npm run sample-data`.

Details, heuristics and data requirements: `../docs/agent-reports/web.md`.
