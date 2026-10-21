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
