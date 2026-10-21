"""Profile builder: the optional single call behind "Draft with Claude" in the domain form."""

import logging

from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine
from app.schemas.domains import DomainProfile, ProfileAnswers

logger = logging.getLogger(__name__)


async def draft_profile(engine: AgentEngine, *, job_id: str, answers: ProfileAnswers) -> RunResult[DomainProfile]:
    """Turns the form answers (and an optional pasted study prompt) into profile text. Nothing is saved."""
    given = "\n".join(
        f"{label}: {value}"
        for label, value in (
            ("Domain name", answers.name),
            ("Purpose", answers.purpose),
            ("Objective", answers.objective),
            ("Depth sections (a note's headings, in order)", "; ".join(s for s in answers.depth_sections if s.strip())),
            ("In scope", answers.scope_include),
            ("Mention only", answers.scope_mention_only),
            ("Style", answers.style),
        )
        if value and value.strip()
    )
    pasted = (
        "\n\nThe owner also pasted the prompt they use to study this domain. Distil it into the profile. Drop anything "
        "about interactive tutoring, quizzes, modes, progress tracking or how a conversation should run; keep only what "
        f"shapes the NOTES themselves: goals, depth, scope, tone.\n<<<pasted prompt\n{answers.pasted_prompt}\n>>>"
        if answers.pasted_prompt and answers.pasted_prompt.strip()
        else ""
    )
    prompt = (
        "You write the profile that steers an AI which writes study notes for one knowledge domain. Fields:\n"
        "- objective: what the notes are for and the depth of understanding wanted.\n"
        "- depth_sections: the ordered headings of a detailed leaf note, each as 'Heading: what that section covers'. "
        "4 to 7 sections.\n"
        "- scope_include: what is in scope, including prerequisites.\n"
        "- scope_mention_only: what may get a single line but never its own note (so notes stay notes, not a book).\n"
        "- style: tone and writing rules.\n\n"
        "Respect everything the owner already wrote and fill the gaps sensibly. Be specific to this domain, not generic.\n\n"
        f"What the owner gave:\n{given or '(nothing typed)'}{pasted}"
    )
    result = await run_structured(engine, role="profile_builder", job_id=job_id, prompt=prompt, model_cls=DomainProfile)
    logger.info("profile drafted for %r (%d depth section(s)); not saved", answers.name or "unnamed domain", len(result.value.depth_sections))
    return result
