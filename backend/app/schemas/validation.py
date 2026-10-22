from pydantic import BaseModel, Field


class Issue(BaseModel):
    code: str
    message: str


class NoteVerdict(BaseModel):
    ok: bool
    issues: list[Issue] = Field(default_factory=list)


class RoundSummary(BaseModel):
    failing_keys: list[str]
    no_progress: bool  # every failing note raised exactly the issue codes it raised last round
    codes: dict[str, list[str]] = Field(default_factory=dict)  # failing key -> its issue codes, for the next round's comparison
    feedback: dict[str, str] = Field(default_factory=dict)  # failing key -> its issues as text for the writer
