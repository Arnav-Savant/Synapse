"""Text / Knowledge Agent prompt contract and structured-output parsing
(spec §7 of docs/superpowers/specs/2026-09-24-multi-agent-architecture-design.md).

The agent runs one continuous session, split into three self-directed
stages (segmentation -> overlap check -> per-topic synthesis), using its
own MCP-scoped toolset (`search_concepts`/`create_concept`/`update_concept`
— see `app/mcp_server/server.py`'s `AgentRole.TEXT_AGENT` tool grant). This
module only builds the prompt that instructs it and parses its final
structured report; it never calls those tools itself — that dispatch is
the Orchestrator's job (`invoke_agent`, spec §6.4).
"""

import json
from dataclasses import dataclass

from app.db.models import Source
from app.orchestrator.tools import SourceSignals


class TextAgentOutputParseError(ValueError):
    """The agent's result_text didn't contain a parseable structured
    output block."""


@dataclass(frozen=True)
class TextAgentOutput:
    segmentation: list[dict]
    overlap_check: dict
    concepts_written: list[dict]
    raw_result_text: str


_OUTPUT_SHAPE = (
    '{"segmentation": [{"title": "...", "scope_description": "...", '
    '"source_excerpt_ref": "..."}], "overlap_check": {"merged_pairs": '
    '[["title-a","title-b"]], "notes": "..."}, "concepts_written": '
    '[{"concept_id": "...", "title": "...", "action": "created"}]}'
)

_REQUIRED_KEYS = ("segmentation", "overlap_check", "concepts_written")


def build_prompt(source: Source, signals: SourceSignals, critique_delta: str | None = None) -> str:
    topic_hint_line = (
        f"The user-provided topic hint for this source is: {signals.topic_hint!r}."
        if signals.topic_hint
        else "No topic hint was provided for this source."
    )

    parts = [
        "You are the Text/Knowledge Agent. Work through this source material in "
        "one continuous session, in three stages, using your own tool calls "
        "(`search_concepts`, `create_concept`, `update_concept`) — do not write "
        "any concept before finishing Stage B.",
        "Source signals:\n"
        f"- content_length: {signals.content_length}\n"
        f"- topic_hint: {signals.topic_hint!r}\n"
        f"- max_title_similarity: {signals.max_title_similarity}\n"
        f"{topic_hint_line}\n"
        "A high max_title_similarity is a hint that an existing concept may "
        "already cover this material, not a directive — look closely for a "
        "genuine dedup match with `search_concepts`, but judge for yourself: a "
        "high score does not mean you must merge, and a low score does not mean "
        "you must create new.",
        "--- Stage A: Segmentation ---\n"
        "Read the source content below in full. Produce a structured list of "
        "candidate topic units. For each candidate, record:\n"
        "- `title`: a concise working title for the topic\n"
        "- `scope_description`: one to two sentences describing exactly what "
        "this candidate does and does not cover\n"
        "- `source_excerpt_ref`: a pointer/quote binding this candidate to the "
        "specific portion of the source content below that it may draw from — "
        "every claim you write for this candidate in Stage C must be grounded "
        "only in this excerpt\n"
        "Do not write anything to the knowledge base yet.",
        "--- Stage B: Overlap check ---\n"
        "Before writing anything, check your candidate list for internal "
        "overlap: for every pair of candidates, does one's scope_description "
        "substantially subsume or repeat the other's? Any such pair must be "
        "merged into a single candidate, or have its scopes clearly redrawn so "
        "the two are disjoint, before you proceed to Stage C.",
        "--- Stage C: Per-topic synthesis ---\n"
        "For each finalized candidate, in order:\n"
        "1. Run the dedup check against the *global* knowledge base using "
        "`search_concepts` — this is a different check than Stage B, which "
        "only compared candidates against each other within this batch.\n"
        "2. If a genuine match exists, call `update_concept` to merge: preserve "
        "what's already there and extend/refine it with what this candidate's "
        "excerpt adds — never wholesale-rewrite or discard existing content.\n"
        "3. If the concept is genuinely new to the graph, call `create_concept`.\n"
        "4. Ground everything you write for this candidate only in its "
        "attributed `source_excerpt_ref` — do not draw on other candidates' "
        "excerpts or on general knowledge beyond the source.",
        "--- Output ---\n"
        "End your final response with a fenced JSON block reporting what you "
        "did, in exactly this shape:\n"
        f"```json\n{_OUTPUT_SHAPE}\n```\n"
        '`action` must be either "created" or "updated". This JSON block must '
        "be the last thing in your response.",
        f"--- Source content (content_length={signals.content_length}) ---\n{source.content}",
    ]

    prompt = "\n\n".join(parts)

    if critique_delta:
        prompt += f"\n\n--- Additional guidance for this run ---\n{critique_delta}"

    return prompt


def parse_output(result_text: str) -> TextAgentOutput:
    """Extracts the fenced/embedded JSON object from result_text, tolerant of
    prose wrapping (Claude Code is observed to sometimes wrap JSON in
    explanatory text despite instruction not to): finds the first '{' and the
    last '}' and attempts json.loads on that span, falling back to trimming
    from the end (searching backwards for an earlier '}') when the naive
    last-'}' span doesn't parse. Raises TextAgentOutputParseError — never
    returns a silently-empty result — if no valid JSON object with all three
    required keys is found.
    """
    start = result_text.find("{")
    if start == -1:
        raise TextAgentOutputParseError(f"no JSON object found in response: {result_text!r}")

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
        raise TextAgentOutputParseError(f"no parseable JSON object found in response: {result_text!r}")

    if not isinstance(data, dict):
        raise TextAgentOutputParseError(f"parsed JSON is not an object: {result_text!r}")

    missing = [key for key in _REQUIRED_KEYS if key not in data]
    if missing:
        raise TextAgentOutputParseError(
            f"parsed JSON is missing required keys {missing}: {result_text!r}"
        )

    return TextAgentOutput(
        segmentation=data["segmentation"],
        overlap_check=data["overlap_check"],
        concepts_written=data["concepts_written"],
        raw_result_text=result_text,
    )
