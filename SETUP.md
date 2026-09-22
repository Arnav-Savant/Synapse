# Setup

**Status: placeholder.** There is no runnable code yet — see
[`docs/PLAN.md`](docs/PLAN.md) Phase 0. This file will be filled in with
real, verified install/run steps as each phase lands, and should always
reflect what's actually true of the repo at HEAD, not aspirational steps.

## What's confirmed available in the target dev environment

(Verified 2026-09-22, Ubuntu 24.04, local machine.)

- Python 3.12.3, Poetry available
- Node v22.22.3, npm 10.9.8
- Claude Code CLI v2.1.278, installed and logged into a paid subscription
  (`~/.claude/.credentials.json` present) — required for the knowledge
  processing engine to work; no `ANTHROPIC_API_KEY` needed for that path.

## Once Phase 0 lands

This section will cover:
1. Initializing/pointing at the knowledge content repository
   (`KNOWLEDGE_REPO_PATH`).
2. Backend install (`cd backend && poetry install`) and run
   (`uvicorn app.main:app --reload`).
3. Frontend install (`cd frontend && npm install`) and run (`npm run dev`).
4. Required `.env` values.

Do not hand-write these steps ahead of the code — follow `docs/PLAN.md`
Phase 0's acceptance criteria and transcribe the steps that actually work.
