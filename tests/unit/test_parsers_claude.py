import json
from harntest.agent.claude_code import ClaudeCodeRunner

parse = ClaudeCodeRunner._parse

INIT = {
    "type": "system",
    "subtype": "init",
    "tools": ["Bash", "Read"],
    "mcp_servers": [],
}
TEXT_BLOCK = {"type": "text", "text": "I will help you."}
TOOL_USE_BLOCK = {
    "type": "tool_use",
    "id": "tu_1",
    "name": "Bash",
    "input": {"command": "echo hello"},
}
SKILL_BLOCK = {
    "type": "tool_use",
    "id": "tu_2",
    "name": "Bash",
    "input": {"command": "/review --foo"},
}
ASSISTANT_TEXT = {
    "type": "assistant",
    "message": {"role": "assistant", "content": [TEXT_BLOCK]},
}
ASSISTANT_TOOL = {
    "type": "assistant",
    "message": {"role": "assistant", "content": [TOOL_USE_BLOCK]},
}
ASSISTANT_SKILL = {
    "type": "assistant",
    "message": {"role": "assistant", "content": [SKILL_BLOCK]},
}
TOOL_RESULT = {
    "type": "tool_result",
    "tool_use_id": "tu_1",
    "content": [{"type": "text", "text": "hello"}],
}
RESULT = {"type": "result", "subtype": "success", "result": "Done"}


def _lines(*msgs) -> str:
    return "\n".join(json.dumps(m) for m in msgs)


def test_text_step():
    run = parse(_lines(INIT, ASSISTANT_TEXT))
    assert len(run.steps) == 1
    assert run.steps[0].type == "text"
    assert run.steps[0].content == "I will help you."


def test_tool_use_step_and_tool_call():
    run = parse(_lines(INIT, ASSISTANT_TOOL))
    assert len(run.steps) == 1
    assert run.steps[0].type == "tool_use"
    assert len(run.tools) == 1
    assert run.tools[0].name == "Bash"
    assert run.tools[0].input == {"command": "echo hello"}
    assert run.tools[0].tool_use_id == "tu_1"


def test_tool_result_step():
    run = parse(_lines(INIT, ASSISTANT_TOOL, TOOL_RESULT))
    tool_result_steps = [s for s in run.steps if s.type == "tool_result"]
    assert len(tool_result_steps) == 1
    assert tool_result_steps[0].content == "hello"


def test_skill_detected():
    run = parse(_lines(INIT, ASSISTANT_SKILL))
    assert run.skills == ["/review"]


def test_skill_not_duplicated():
    run = parse(_lines(INIT, ASSISTANT_SKILL, ASSISTANT_SKILL))
    assert run.skills == ["/review"]


def test_non_skill_bash_not_in_skills():
    run = parse(_lines(INIT, ASSISTANT_TOOL))
    assert run.skills == []


def test_malformed_lines_skipped():
    stdout = "not json\n" + json.dumps(INIT) + "\nalso bad\n" + json.dumps(RESULT)
    run = parse(stdout)
    assert len(run.steps) == 0


def test_raw_is_full_stdout():
    stdout = _lines(INIT, ASSISTANT_TEXT, RESULT)
    run = parse(stdout)
    assert run.raw == stdout


def test_multi_block_assistant():
    msg = {
        "type": "assistant",
        "message": {"role": "assistant", "content": [TEXT_BLOCK, TOOL_USE_BLOCK]},
    }
    run = parse(_lines(INIT, msg))
    assert len(run.steps) == 2
    assert run.steps[0].type == "text"
    assert run.steps[1].type == "tool_use"
    assert len(run.tools) == 1


def test_tool_result_string_content():
    result_msg = {
        "type": "tool_result",
        "tool_use_id": "tu_1",
        "content": "plain string",
    }
    run = parse(_lines(INIT, result_msg))
    tr = [s for s in run.steps if s.type == "tool_result"]
    assert tr[0].content == "plain string"
