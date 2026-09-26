"""Graph Agent prompt contract and structured-output parsing (spec §4.3,
§6.2, §8 of docs/superpowers/specs/2026-09-24-multi-agent-architecture-design.md).

The agent runs after a Text Agent round, using its own MCP-scoped toolset
(`get_graph_neighborhood`, `search_relationships`, `get_concept_metadata`,
`add_relationship`, `update_relationship`, `remove_relationship` — see
`app/mcp_server/server.py`'s `AgentRole.GRAPH_AGENT` tool grant). This
module only builds the prompt that instructs it and parses its final
structured report; it never calls those tools itself — that dispatch is
the Orchestrator's job (`invoke_agent`, spec §6.4).

Deliberate information asymmetry with the Text Agent (spec §6.2): the
Graph Agent never sees concept body content, only title/category via
`get_concept_metadata`. It must reason from graph topology alone, which is
also why its `justification` for a proposed relationship (spec §8 Layer 2)
must cite topological evidence it actually observed via a tool call this
round, never a text quote — it structurally has no source text to quote.
"""

import json
from dataclasses import dataclass

from app.repositories.graph_repo import (
    DIRECTIONAL_NOT_HIERARCHICAL_TYPES,
    HIERARCHICAL_TYPES,
    SYMMETRIC_TYPES,
)


class GraphAgentOutputParseError(ValueError):
    """The agent's result_text didn't contain a parseable structured
    output block."""


@dataclass(frozen=True)
class GraphAgentOutput:
    relationships_written: list[dict]
    raw_result_text: str


_OUTPUT_SHAPE = (
    '{"relationships_written": [{"source_id": "...", "target_id": "...", '
    '"type": "...", "action": "created"}]}'
)

_REQUIRED_KEYS = ("relationships_written",)


def _format_type_taxonomy() -> str:
    lines = [
        "- Hierarchical types (must not form cycles — Layer 1 rejects any edge "
        "that would close a cycle in the same-type subgraph): "
        + ", ".join(sorted(HIERARCHICAL_TYPES)),
        "- Symmetric types (Layer 1 rejects declaring the same relationship on "
        "both sides — propose it once, in either direction, never twice): "
        + ", ".join(sorted(SYMMETRIC_TYPES)),
        "- Directional, non-hierarchical types (plain directional edges, not "
        "subject to the cycle check): " + ", ".join(sorted(DIRECTIONAL_NOT_HIERARCHICAL_TYPES)),
    ]
    return "\n".join(lines)


def build_prompt(concepts_written: list[dict]) -> str:
    concepts_lines = "\n".join(
        f"- concept_id={c['concept_id']!r}, title={c['title']!r}" for c in concepts_written
    )

    parts = [
        "You are the Graph Agent. The Text Agent just finished a round and "
        "wrote/updated the following concepts:\n"
        f"{concepts_lines}",
        "--- Mandatory first step, non-negotiable ---\n"
        "Before doing anything else, call `get_concept_metadata` on every "
        "concept_id listed above, one by one. This is not just informational "
        "context-gathering: `get_concept_metadata`'s implementation is the "
        "only mechanism that upserts the thin graph node for a concept the "
        "Text Agent just wrote. If you skip this, `add_relationship` will "
        "fail with a not-found error for every brand-new concept above. Do "
        "this first, for every concept_id, before any exploration or "
        "relationship proposal.",
        "This same rule extends to any *other* concept you consider relating "
        "to — one you find via `search_relationships` or "
        "`get_graph_neighborhood` exploration that may predate this round. "
        "Call `get_concept_metadata` on **both** endpoints of any proposed "
        "edge before calling `add_relationship`, not just this round's own "
        "concepts — an endpoint that predates this round but whose node "
        "you've never fetched is exactly as unsafe to reference as a "
        "brand-new one you skipped.",
        "--- Tool boundary: you only see title/category, never body content ---\n"
        "`get_concept_metadata` returns only `id`, `title`, and `category` — "
        "you are never given a concept's body content, by design. Reason "
        "only from graph topology: existing edges (`search_relationships`), "
        "neighborhood density and structure (`get_graph_neighborhood`), and "
        "category alignment. Never assume content you haven't been given, "
        "and never treat a title/category match alone as sufficient — look "
        "for actual topological evidence.",
        "--- Relationship type taxonomy ---\n" + _format_type_taxonomy(),
        "--- Justification requirement ---\n"
        "Every `add_relationship` call requires a `justification` argument. "
        "Because you never have access to source text, your justification "
        "must cite the specific topological evidence you actually observed "
        "via a tool call this round — for example, \"X and Y share 3 "
        "committed neighbors under `related-to`\" or \"X's category matches "
        "an existing `subtopic-of` cluster rooted at Z\" — never a "
        "fabricated text quote. A justification that reads like a quote from "
        "source material is wrong for this agent; ground it in topology you "
        "observed, not in text you were never given.",
        "--- Your task ---\n"
        "For each concept above (and any other concept you find worth "
        "relating to it), explore the graph via `get_graph_neighborhood` and "
        "`search_relationships`, decide whether any new relationships are "
        "warranted, and propose them via `add_relationship` (or "
        "`update_relationship`/`remove_relationship` if you find an existing "
        "edge that needs correcting). Only propose a relationship when you "
        "have real topological evidence to justify it — silence (no edge) is "
        "better than a hallucinated connection.",
        "--- Output ---\n"
        "End your final response with a fenced JSON block reporting what you "
        "did, in exactly this shape:\n"
        f"```json\n{_OUTPUT_SHAPE}\n```\n"
        '`action` must be one of "created", "updated", or "removed". This '
        "JSON block must be the last thing in your response.",
    ]

    return "\n\n".join(parts)


def parse_output(result_text: str) -> GraphAgentOutput:
    """Extracts the fenced/embedded JSON object from result_text, tolerant of
    prose wrapping (Claude Code is observed to sometimes wrap JSON in
    explanatory text despite instruction not to): finds the first '{' and the
    last '}' and attempts json.loads on that span, falling back to trimming
    from the end (searching backwards for an earlier '}') when the naive
    last-'}' span doesn't parse. Raises GraphAgentOutputParseError — never
    returns a silently-empty result — if no valid JSON object with the
    required key is found.
    """
    start = result_text.find("{")
    if start == -1:
        raise GraphAgentOutputParseError(f"no JSON object found in response: {result_text!r}")

    end = result_text.rfind("}")
    data = None
    while end > start:
        candidate = result_text[start : end + 1]
        try:
            data = json.loads(candidate)
            break
        except json.JSONDecodeError:
            end = result_text.rfind("}", start, end)

    if data is None:
        raise GraphAgentOutputParseError(f"no parseable JSON object found in response: {result_text!r}")

    if not isinstance(data, dict):
        raise GraphAgentOutputParseError(f"parsed JSON is not an object: {result_text!r}")

    missing = [key for key in _REQUIRED_KEYS if key not in data]
    if missing:
        raise GraphAgentOutputParseError(
            f"parsed JSON is missing required keys {missing}: {result_text!r}"
        )

    return GraphAgentOutput(
        relationships_written=data["relationships_written"],
        raw_result_text=result_text,
    )
