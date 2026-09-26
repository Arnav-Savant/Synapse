"""Validation Agent prompt contract and structured-output parsing (spec
§4.4, §5.2, §6.3, §8 Layer 3 of
docs/superpowers/specs/2026-09-24-multi-agent-architecture-design.md).

The agent is read-only across both concept content and graph structure
(§6.3: `get_concept`, `get_graph_neighborhood`, `search_concepts` — no
write tools at all) and never writes — its only output is a structured
critique (§5.2): `{verdict: pass|reject, issues: [{category, severity,
target_id, description}]}`. It is deliberately tuned to favor precision
over recall (§4.4): a hallucinated connection actively misleads later
study, while a missed connection self-heals next time related material is
ingested, so rejecting on doubt is the right default.

This module only builds the prompt that instructs it and parses its final
structured report; it never calls read tools itself — that dispatch is the
Orchestrator's job (`invoke_agent`, spec §6.4). It also has no knowledge of
the retry loop that consumes its critique (spec §5.2's additive delta
prompting and no-progress detection) — that lives in the Orchestrator,
not here.
"""

from dataclasses import dataclass

from app.agents.structured_output import extract_json_object

# Closed taxonomy of validation-issue categories. Each category is grounded
# in a specific spec passage (cited inline) and belongs to exactly one
# specialist, since the Orchestrator's retry loop (§5.2) re-invokes "only
# the agent responsible for the flagged issue" — an issue category that
# didn't map cleanly to one agent would break that targeted re-invocation.

TEXT_AGENT_CATEGORIES = (
    # §7 Stage C: "Ground everything you write for this candidate only in
    # its attributed source_excerpt_ref" — content not actually supported
    # by the source it claims to draw from.
    "ungrounded_content",
    # §7 Stage C: "run the existing dedup check against the *global*
    # knowledge base" — a genuine match existed but wasn't merged.
    "missed_duplicate",
    # §7 Stage B: "does any pair's scope_description substantially subsume
    # or repeat another's?" — the self-consistency check should have
    # caught this before synthesis.
    "scope_overlap",
    # §7 Backstop: "a cheap title/content similarity check ... catching
    # over-fragmentation that slipped past Stage B's self-check."
    "unwarranted_fragmentation",
)

GRAPH_AGENT_CATEGORIES = (
    # §8 Layer 3: "does the justification actually support the claim?"
    "unsupported_justification",
    # §8 Layer 3: "Is the relationship type appropriate given what the
    # justification says (not just structurally valid)?"
    "incorrect_relationship_type",
    # §8 Layer 3: "Does it duplicate an existing edge's intent even if not
    # byte-identical?"
    "duplicate_relationship_intent",
)


def target_agent_for_category(category: str) -> str:
    """Maps a validation-issue category to the specialist responsible for
    fixing it, so the Orchestrator's retry loop (§5.2) can re-invoke "only
    the agent responsible for the flagged issue" rather than the whole
    pipeline. Raises ValueError for any category outside the closed
    taxonomy above — this is not an open-ended classification.
    """
    if category in TEXT_AGENT_CATEGORIES:
        return "text_agent"
    if category in GRAPH_AGENT_CATEGORIES:
        return "graph_agent"
    raise ValueError(f"unrecognized validation issue category: {category!r}")


class ValidationAgentOutputParseError(ValueError):
    """The agent's result_text didn't contain a parseable structured
    output block."""


@dataclass(frozen=True)
class ValidationAgentOutput:
    verdict: str
    issues: list[dict]
    raw_result_text: str


_OUTPUT_SHAPE = (
    '{"verdict": "pass", "issues": [{"category": "...", "severity": "...", '
    '"target_id": "...", "description": "..."}]}'
)

_REQUIRED_KEYS = ("verdict", "issues")


def _format_concepts_written(text_agent_result: dict) -> str:
    concepts_written = text_agent_result.get("concepts_written", [])
    if not concepts_written:
        return "(no concepts written this round)"
    return "\n".join(
        f"- concept_id={c.get('concept_id')!r}, title={c.get('title')!r}, "
        f"action={c.get('action')!r}"
        for c in concepts_written
    )


def _format_relationships_written(graph_agent_result: dict) -> str:
    relationships_written = graph_agent_result.get("relationships_written", [])
    if not relationships_written:
        return "(no relationships written this round)"
    return "\n".join(
        f"- source_id={r.get('source_id')!r}, target_id={r.get('target_id')!r}, "
        f"type={r.get('type')!r}, action={r.get('action')!r}"
        for r in relationships_written
    )


def build_prompt(text_agent_result: dict, graph_agent_result: dict | None = None) -> str:
    parts = [
        "You are the Validation Agent. You are read-only across both concept "
        "content and graph structure (`get_concept`, `get_graph_neighborhood`, "
        "`search_concepts`) and have no write tools at all — your only output "
        "is the structured critique described below.",
        "You are tuned to favor precision over recall: a hallucinated "
        "connection actively misleads later study, while a missed connection "
        "self-heals the next time related material is ingested. Reject on "
        "doubt rather than let something questionable pass.",
        "--- Text Agent output this round ---\n" + _format_concepts_written(text_agent_result),
    ]

    if graph_agent_result is not None:
        parts.append(
            "--- Graph Agent output this round ---\n"
            + _format_relationships_written(graph_agent_result)
        )
    else:
        parts.append(
            "--- Graph Agent did not run this round ---\n"
            "Only the Text Agent output above needs validation; no "
            "relationship edges were proposed this round."
        )

    parts.append(
        "--- What to check ---\n"
        "For each concept written: is its content actually grounded in the "
        "source it claims to draw from, or does it read like it drifted "
        "beyond that? Does it genuinely duplicate an existing concept that "
        "should have been merged instead? Does its scope substantially "
        "overlap another concept written this round? Does the batch show "
        "unwarranted fragmentation of what should have been one concept?\n"
        "For each relationship written (if any): does the justification "
        "actually support the claimed relationship, or does it merely "
        "gesture at a connection without establishing it? Is the "
        "relationship type appropriate given what the justification says, "
        "not just structurally valid? Does it duplicate an existing edge's "
        "intent even if not byte-identical?\n"
        "Use your read tools to verify against the actual state of the "
        "knowledge base — do not judge from the summaries above alone."
    )

    parts.append(
        "--- Closed issue-category taxonomy ---\n"
        "Every issue you report must use exactly one of these category "
        "names — do not invent others:\n"
        "Text Agent categories: " + ", ".join(TEXT_AGENT_CATEGORIES) + "\n"
        "Graph Agent categories: " + ", ".join(GRAPH_AGENT_CATEGORIES)
    )

    parts.append(
        "--- Output ---\n"
        "End your final response with a fenced JSON block reporting your "
        "verdict, in exactly this shape:\n"
        f"```json\n{_OUTPUT_SHAPE}\n```\n"
        '`verdict` must be either "pass" or "reject". If `verdict` is '
        '"pass", `issues` must be an empty list. Every issue\'s `category` '
        "must be one of the closed taxonomy names above and `target_id` "
        "must identify the specific concept or relationship it concerns. "
        "This JSON block must be the last thing in your response."
    )

    return "\n\n".join(parts)


def parse_output(result_text: str) -> ValidationAgentOutput:
    """Extracts the fenced/embedded JSON object from result_text, tolerant of
    prose wrapping (Claude Code is observed to sometimes wrap JSON in
    explanatory text despite instruction not to), via
    `structured_output.extract_json_object`. Raises
    ValidationAgentOutputParseError — never returns a silently-empty result
    — if no valid JSON object with both required keys is found.
    """
    data = extract_json_object(result_text, _REQUIRED_KEYS, ValidationAgentOutputParseError)

    return ValidationAgentOutput(
        verdict=data["verdict"],
        issues=data["issues"],
        raw_result_text=result_text,
    )
