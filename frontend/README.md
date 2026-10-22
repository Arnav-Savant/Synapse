# Synapse frontend

The Synapse web app: React, TypeScript, Vite, Tailwind CSS and TanStack Query.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to the backend on 127.0.0.1:8000
npm run build    # type-check and production build
npm run lint
```

The backend must be running for anything beyond the shell to work; see the root
[`SETUP.md`](../SETUP.md).

## Layout

| Folder | Contents |
|---|---|
| `src/api/` | Typed clients, one per backend area. `client.ts` is the only code that calls `fetch`. |
| `src/design/` | Colour, type and spacing tokens (`tokens.css`) and the shared primitives: button, chip, card, form fields, empty state, spinner. |
| `src/shell/` | The sidebar (with the live "needs you" count) and the page frame with its sticky action bar. |
| `src/features/ingest/` | Submit a topic or pasted material. |
| `src/features/jobs/` | The jobs dashboard, the pipeline trail and the read-only job view. |
| `src/features/outline/` | The outline approval screen and its pure tree-editing helpers. |
| `src/features/drafts/` | The draft review screen: list, preview, diff, feedback form and the decision builder. |
| `src/features/notes/` | The notes list and the delete preview dialog. |
| `src/features/settings/` | Domain management and per-agent model settings. |

There is no router: four top-level views are held in state, and the two approval screens open
from inside Jobs. Colours always come from the semantic tokens (`bg-surface`, `text-muted`,
`bg-accent`, and so on), never from literal values, so light and dark themes stay in step with the
operating system. Server state lives in TanStack Query; everything else is local component state.
