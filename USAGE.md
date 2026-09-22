# Usage

**Status: placeholder.** There is no user-facing app yet — see
[`docs/PLAN.md`](docs/PLAN.md) for the build order. This file will describe
real workflows as their phases land.

## Planned day-to-day workflow (for reference — not usable yet)

1. **Add source material** — paste a ChatGPT/Claude/Gemini conversation (or
   an article, note, etc.) into the app, or drop a file directly into the
   knowledge repository's `source/<category>/` folder. (Phase 1)
2. **Process it** — trigger processing on that source file from the app;
   Claude Code reads it plus your existing knowledge base and creates or
   updates concept files, watch the job status until it completes. (Phase 2)
3. **Study via the graph** — open the global graph, search or browse to a
   concept, select it to read the synthesized notes. Use domain/status
   filters and the focus view to navigate dense areas. (Phases 3–4)
4. **Read and refine** — read the generated notes (not the raw
   conversation), follow `[[links]]` to related concepts, edit notes
   directly when you want to correct or extend them, and check "sources" on
   a concept if you want to see the original raw material it came from.
   (Phase 5)
5. **Ask questions** — use the chat panel to ask questions answered from
   your knowledge base; works with no configuration. (Phase 6)
6. **(Optional) Use an external model** — configure an API key and pick a
   provider/model in Settings if you want chat to use something other than
   Claude Code. (Phase 7)

Each numbered step becomes real and documented with actual screenshots/steps
as its phase completes — this list will be replaced, not just appended to.
