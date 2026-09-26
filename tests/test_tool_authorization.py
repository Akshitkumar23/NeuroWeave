import pytest
import asyncio
from core.tool_registry import registry, ToolRegistry
import tools.code_executor
import tools.web_search


@pytest.mark.anyio
async def test_authorized_agent_can_execute_allowed_tool():
    """Verify an agent with legitimate tool access can execute the tool."""
    res = await registry.execute(
        tool_name="web_search",
        agent_name="researcher",
        args={"query": "test postgresql architecture"},
        session_id="sess_auth_test_1",
        task_id="task_res_1"
    )
    assert res["success"] is True
    assert res["status"] == "EXECUTED"
    assert "result" in res


@pytest.mark.anyio
async def test_unauthorized_agent_is_denied():
    """Verify an unauthorized agent is explicitly denied with TOOL_ACCESS_DENIED."""
    res = await registry.execute(
        tool_name="code_executor",
        agent_name="researcher",  # researcher is NOT in code_executor allowed_agents
        args={"code": "1 + 1"},
        session_id="sess_auth_test_2",
        task_id="task_res_2"
    )
    assert res["success"] is False
    assert res["status"] == "TOOL_ACCESS_DENIED"
    assert "Security Violation" in res["error"]


@pytest.mark.anyio
async def test_persona_bound_tool_authorization():
    """Verify that if a persona lacks a tool, execution is denied even if the general agent role is authorized."""
    # A persona with only marketing tools cannot execute python_sandbox / code_executor
    res = await registry.execute(
        tool_name="code_executor",
        agent_name="analyzer",
        args={"code": "1 + 1"},
        persona_id="marketing_analyst",
        persona_bound_tools=["seo_extractor", "sentiment_analyzer"],
        session_id="sess_auth_test_3",
        task_id="task_res_3"
    )
    assert res["success"] is False
    assert res["status"] == "TOOL_ACCESS_DENIED"


@pytest.mark.anyio
async def test_tool_execution_telemetry_recorded():
    """Verify that every tool call, whether authorized or denied, is recorded in telemetry."""
    session_id = "sess_telemetry_test_99"
    registry.clear_telemetry(session_id)

    # 1. Allowed call
    await registry.execute(
        tool_name="code_executor",
        agent_name="analyzer",
        args={"code": "result = 42 * 2"},
        session_id=session_id,
        task_id="task_allowed_99"
    )

    # 2. Denied call
    await registry.execute(
        tool_name="code_executor",
        agent_name="unauthorized_agent",
        args={"code": "import os"},
        session_id=session_id,
        task_id="task_denied_99"
    )

    records = registry.get_telemetry(session_id)
    assert len(records) == 2

    allowed_rec = next(r for r in records if r["task_id"] == "task_allowed_99")
    assert allowed_rec["auth_status"] == "AUTHORIZED"
    assert allowed_rec["success"] is True

    denied_rec = next(r for r in records if r["task_id"] == "task_denied_99")
    assert denied_rec["auth_status"] == "DENIED"
    assert denied_rec["success"] is False
    assert "Security Violation" in denied_rec["error"]
