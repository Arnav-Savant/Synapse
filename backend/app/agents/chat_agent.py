"""Chat prompt contract (docs/ARCHITECTURE.md §10). Chat is read-only Q&A,
scoped to `search_concepts`/`get_concept`/`get_graph_neighborhood`
(`app/mcp_server/server.py`'s `AgentRole.CHAT` tool grant). Unlike
`text_agent.py`, there's no structured-output contract to parse — the
agent's final response is returned directly as `EngineResult.result_text`,
so this module only builds the prompt.
"""


def build_prompt(message: str, concept_id: str | None) -> str:
    if concept_id:
        concept_context = (
            f"The user is currently viewing concept `{concept_id}` in the UI. "
            "Consider looking it up first with `get_concept`, but it isn't "
            "necessarily the only concept relevant to their question — use "
            "`search_concepts` and `get_graph_neighborhood` as needed too."
        )
    else:
        concept_context = "The user isn't currently viewing any particular concept."

    parts = [
        "You are the Synapse chat assistant, answering questions about the "
        "user's personal knowledge graph. You have read-only tools available "
        "— `search_concepts`, `get_concept`, `get_graph_neighborhood` — and "
        "no tools that can create, update, or delete anything. Never claim "
        "to have changed the knowledge base.",
        concept_context,
        "Look up whatever knowledge is actually relevant before answering — "
        "don't rely on general knowledge when the graph has something "
        "concrete to say, and don't guess at concept content you haven't "
        "read via a tool call.",
        "Answer directly in natural language. Do not wrap your answer in "
        "JSON or any other structured format.",
        f"--- User question ---\n{message}",
    ]

    return "\n\n".join(parts)
