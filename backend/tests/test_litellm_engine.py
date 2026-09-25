import asyncio

import pytest

from app.engines.base import AgentEngine, EngineInvocation
from app.engines.litellm_engine import LiteLLMEngine, LiteLLMNotConfiguredError


def test_litellm_engine_satisfies_agent_engine_protocol():
    assert isinstance(LiteLLMEngine(), AgentEngine)


def test_invoke_raises_not_configured_error_with_role_in_message():
    invocation = EngineInvocation(agent_role="researcher", job_id="job-1", prompt="do the thing")

    with pytest.raises(LiteLLMNotConfiguredError) as exc_info:
        asyncio.run(LiteLLMEngine().invoke(invocation))

    assert "researcher" in str(exc_info.value)
