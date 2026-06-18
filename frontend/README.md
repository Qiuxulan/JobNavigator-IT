# JobNavigator-IT Frontend

React + TypeScript + Vite frontend for the JobNavigator-IT integrated demo.

## Pages

- Dashboard: 69 IT roles, demand ranking, category trend overview, trend distribution.
- Role detail: 24-month PatchTST trend curve, evidence summary and CoT context entry.
- Role comparison: compare multiple roles by predicted demand index and direction.
- Knowledge graph: role-skill-event graph with category filters.
- Learning path: generate skill-gap based learning path and resources.
- AI assistant: real Agent API chat for trend, role, skill-gap and path questions.

## Local Run

```bash
npm install
npm run dev
```

The Vite dev server proxies `/api` to the FastAPI backend at `127.0.0.1:8000`.

## Build

```bash
npm run build
```

The generated `dist/` directory is ignored by Git and should be rebuilt during deployment.
