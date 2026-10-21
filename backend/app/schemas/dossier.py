"""Research output: facts with their sources, and the references a note ends with."""

from typing import Literal

from pydantic import BaseModel, Field

SourceKind = Literal["official", "maintainer", "community", "article"]
KIND_RANK: dict[str, int] = {"official": 0, "maintainer": 1, "community": 2, "article": 3}

DEFAULT_MAX_TURNS = 12
DEFAULT_MAX_SEARCHES = 8
DEFAULT_TIMEOUT_SECONDS = 600


class Source(BaseModel):
    url: str
    title: str
    kind: SourceKind


class Fact(BaseModel):
    text: str
    source_urls: list[str] = Field(default_factory=list)


class Dossier(BaseModel):
    node_key: str
    facts: list[Fact]
    sources: list[Source]


class Reference(BaseModel):
    url: str
    title: str
    kind: SourceKind
    note: str = Field(description="one line on what this link is good for")


class ReferenceList(BaseModel):
    references: list[Reference]


class ResearchBudget(BaseModel):
    max_turns: int = DEFAULT_MAX_TURNS
    max_searches: int = DEFAULT_MAX_SEARCHES
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_params(cls, params: dict | None) -> "ResearchBudget":
        """Reads `agent_config.params`; missing or non-positive values fall back to the defaults."""
        params = params or {}
        fields = {k: int(params[k]) for k in cls.model_fields if isinstance(params.get(k), (int, float)) and params[k] > 0}
        return cls(**fields)
