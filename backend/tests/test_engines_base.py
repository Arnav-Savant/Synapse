from app.engines.base import AgentEngine, EngineInvocation, EngineResult


class FakeEngine:
    async def invoke(self, invocation: EngineInvocation) -> EngineResult:
        return EngineResult(is_error=False, result_text="ok", cost_usd=None)


class NotAnEngine:
    async def run(self, invocation: EngineInvocation) -> EngineResult:
        return EngineResult(is_error=False, result_text="ok", cost_usd=None)


def test_fake_engine_satisfies_agent_engine_protocol():
    assert isinstance(FakeEngine(), AgentEngine)


def test_class_without_invoke_does_not_satisfy_agent_engine_protocol():
    assert not isinstance(NotAnEngine(), AgentEngine)


def test_engine_invocation_defaults():
    invocation = EngineInvocation(agent_role="critic", job_id="job-1", prompt="do the thing")

    assert invocation.tool_names == ()
    assert invocation.timeout_seconds == 300


def test_engine_result_default_raw_metadata_is_empty_dict():
    result = EngineResult(is_error=False, result_text="ok", cost_usd=0.01)

    assert result.raw_metadata == {}


def test_engine_result_default_raw_metadata_not_shared_between_instances():
    first = EngineResult(is_error=False, result_text="ok", cost_usd=None)
    second = EngineResult(is_error=False, result_text="ok", cost_usd=None)

    assert first.raw_metadata is not second.raw_metadata

    first.raw_metadata["key"] = "value"

    assert "key" not in second.raw_metadata
