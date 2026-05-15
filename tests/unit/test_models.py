from tea.agent.agent_run import AgentRun, Step, ToolCall


def test_tool_call_fields():
    tc = ToolCall(name="Bash", input={"command": "ls"}, tool_use_id="tu_1")
    assert tc.name == "Bash"
    assert tc.input == {"command": "ls"}
    assert tc.tool_use_id == "tu_1"


def test_step_fields():
    s = Step(type="text", content="hello", raw={"type": "text", "text": "hello"})
    assert s.type == "text"
    assert s.content == "hello"


def test_agent_run_defaults():
    run = AgentRun(raw="", steps=[], tools=[], skills=[])
    assert run.exit_code == 0
    assert run.stderr == ""


def test_agent_run_full():
    steps = [Step(type="text", content="hi", raw={})]
    tools = [ToolCall(name="Read", input={"path": "/tmp"}, tool_use_id="tu_1")]
    run = AgentRun(
        raw="some output", steps=steps, tools=tools, skills=["/review"], exit_code=0
    )
    assert run.raw == "some output"
    assert len(run.steps) == 1
    assert len(run.tools) == 1
    assert run.skills == ["/review"]
