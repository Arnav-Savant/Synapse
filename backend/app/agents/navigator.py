"""Navigator: finds the notes in the vault map that could hold the answer to a task."""

import logging
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.agents.prompt_parts import UNTRUSTED_NOTES
from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine
from app.schemas.chat_agents import Pick, ToolRecord, VaultMap, log_block
from app.vault.titles import title_key

logger = logging.getLogger(__name__)

MAX_PICKS = 12


class SearchVault(BaseModel):
    action: Literal["search_vault"]
    terms: list[str] = Field(min_length=1, max_length=5, description="words or phrases to look for in the note files")


class NavigatorFinish(BaseModel):
    action: Literal["finish"]
    picks: list[Pick] = Field(max_length=MAX_PICKS, description="notes to read, each a note in the map, with why")
    missing: list[str] = Field(description="concepts the task needs that no note in the map covers")


class NavigatorReply(BaseModel):
    step: Annotated[SearchVault | NavigatorFinish, Field(discriminator="action")]


async def navigator_step(
    engine: AgentEngine,
    *,
    run_id: str,
    task: str,
    vault_map: VaultMap,
    log: list[ToolRecord],
    max_steps: int = 3,
) -> RunResult[SearchVault | NavigatorFinish]:
    """One call of a navigator run. The runtime carries out `search_vault` and calls again with the log."""

    class _Reply(NavigatorReply):
        @model_validator(mode="after")
        def _picks_exist(self) -> "_Reply":
            if isinstance(self.step, NavigatorFinish):
                unknown = [
                    p.title for p in self.step.picks if title_key(p.title) not in vault_map.keys.get(p.domain, set())
                ]
                if unknown:
                    raise ValueError(f"these picks are not notes in the map (check the domain and the exact title): {unknown}")
            return self

    prompt = (
        "You are the navigator of a study chat. Find the notes in the owner's vaults that could hold what the task needs.\n"
        "Map the task to the concepts it involves, including notes it never names: a question about how a system works "
        "is often answered by a note on the technique underneath it. Use the map's titles, summaries, parents and related "
        "links to find them. Include the neighbours an answer needs (prerequisites, contrasts), not only the closest match.\n"
        f"{UNTRUSTED_NOTES}\n\n"
        f"Task: {task}\n\n"
        f"Vault map:\n{vault_map.text}\n\n"
        f"What you have done so far in this run:\n{log_block(log)}\n\n"
        f"Step budget: this is step {len(log) + 1} of {max_steps}. "
        "You may `search_vault` for terms to look inside the note files when the map is not enough. "
        f"Otherwise `finish` with up to {MAX_PICKS} picks, each copied exactly from the map as domain and title with the reason "
        "it matters, and list under `missing` the concepts no note covers. If no note is relevant, or the map has no notes, "
        "finish with no picks. On the last step you must finish."
    )
    result = await run_structured(engine, role="navigator", job_id=run_id, prompt=prompt, model_cls=_Reply)
    step = result.value.step
    logger.info("navigator step %d: %s", len(log) + 1, step.action)
    return RunResult(value=step, cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)
