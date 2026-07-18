import json

from tea.agent.agent_run import StepType
from tea.agent.pi import _parse

SESSION = {"type": "session", "version": 3, "id": "abc123", "cwd": "/workspace"}
AGENT_START = {"type": "agent_start"}
TURN_START = {"type": "turn_start"}
AGENT_END = {"type": "agent_end", "messages": []}

TEXT_MESSAGE_END = {
    "type": "message_end",
    "message": {
        "role": "assistant",
        "content": [{"type": "text", "text": "I will help you."}],
    },
}

MULTI_TEXT_MESSAGE_END = {
    "type": "message_end",
    "message": {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "First sentence."},
            {"type": "text", "text": "Second sentence."},
        ],
    },
}

EMPTY_MESSAGE_END = {
    "type": "message_end",
    "message": {"role": "assistant", "content": []},
}

TOOL_START = {
    "type": "tool_execution_start",
    "toolCallId": "tc_1",
    "toolName": "bash",
    "args": {"command": "ls -la"},
}

TOOL_END = {
    "type": "tool_execution_end",
    "toolCallId": "tc_1",
    "toolName": "bash",
    "result": "total 0\ndrwxr-xr-x 2 node node 40 Jan 1 00:00 .",
    "isError": False,
}

TOOL_END_DICT_RESULT = {
    "type": "tool_execution_end",
    "toolCallId": "tc_1",
    "toolName": "read",
    "result": {"content": "file contents", "path": "/workspace/foo.py"},
    "isError": False,
}

UNKNOWN_EVENT = {"type": "queue_update", "steering": [], "followUp": []}


def _lines(*events) -> str:
    return "\n".join(json.dumps(e) for e in events)


def test_text_step():
    run = _parse(_lines(SESSION, AGENT_START, TEXT_MESSAGE_END, AGENT_END))
    assert len(run.steps) == 1
    assert run.steps[0].type == StepType.TEXT
    assert run.steps[0].content == "I will help you."


def test_multi_text_blocks_in_one_message():
    run = _parse(_lines(SESSION, MULTI_TEXT_MESSAGE_END))
    text_steps = [s for s in run.steps if s.type == StepType.TEXT]
    assert len(text_steps) == 2
    assert text_steps[0].content == "First sentence."
    assert text_steps[1].content == "Second sentence."


def test_empty_message_produces_no_text_step():
    run = _parse(_lines(SESSION, EMPTY_MESSAGE_END))
    assert run.steps == []


def test_user_message_end_is_ignored():
    user_msg_end = {
        "type": "message_end",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "the prompt"}],
        },
    }
    run = _parse(_lines(SESSION, user_msg_end, TEXT_MESSAGE_END))
    assert len(run.steps) == 1
    assert run.steps[0].content == "I will help you."


def test_tool_use_step_and_tool_call():
    run = _parse(_lines(SESSION, TOOL_START))
    assert len(run.steps) == 1
    assert run.steps[0].type == StepType.TOOL_USE
    assert len(run.tools) == 1
    assert run.tools[0].name == "bash"
    assert run.tools[0].tool_use_id == "tc_1"
    assert run.tools[0].input == {"command": "ls -la"}


def test_tool_result_step_string():
    run = _parse(_lines(SESSION, TOOL_START, TOOL_END))
    tool_result_steps = [s for s in run.steps if s.type == StepType.TOOL_RESULT]
    assert len(tool_result_steps) == 1
    assert "total 0" in tool_result_steps[0].content


def test_tool_result_step_dict():
    run = _parse(_lines(SESSION, TOOL_END_DICT_RESULT))
    tool_result_steps = [s for s in run.steps if s.type == StepType.TOOL_RESULT]
    assert len(tool_result_steps) == 1
    assert "file contents" in tool_result_steps[0].content


def test_mixed_sequence_ordering():
    run = _parse(
        _lines(SESSION, TEXT_MESSAGE_END, TOOL_START, TOOL_END, TEXT_MESSAGE_END)
    )
    assert run.steps[0].type == StepType.TEXT
    assert run.steps[1].type == StepType.TOOL_USE
    assert run.steps[2].type == StepType.TOOL_RESULT
    assert run.steps[3].type == StepType.TEXT
    assert len(run.tools) == 1


def test_unknown_event_types_skipped():
    run = _parse(_lines(SESSION, UNKNOWN_EVENT, AGENT_START, TURN_START, AGENT_END))
    assert run.steps == []
    assert run.tools == []


def test_malformed_lines_skipped():
    stdout = "not json\n" + json.dumps(TEXT_MESSAGE_END) + "\nalso bad\n"
    run = _parse(stdout)
    assert len(run.steps) == 1
    assert run.steps[0].type == StepType.TEXT


def test_empty_output():
    run = _parse("")
    assert run.steps == []
    assert run.tools == []
    assert run.skills == []
    assert run.raw == ""


def test_raw_is_full_stdout():
    stdout = _lines(SESSION, TEXT_MESSAGE_END)
    run = _parse(stdout)
    assert run.raw == stdout


def test_skills_always_empty():
    # Pi does not emit skill invocations in its output
    run = _parse(_lines(SESSION, TEXT_MESSAGE_END, TOOL_START))
    assert run.skills == []


def test_message_end_with_string_content():
    event = {
        "type": "message_end",
        "message": {"role": "assistant", "content": "raw string body"},
    }
    run = _parse(_lines(SESSION, event))
    assert len(run.steps) == 1
    assert run.steps[0].type == StepType.TEXT
    assert run.steps[0].content == "raw string body"


def test_tool_execution_start_non_dict_args_falls_back_to_empty():
    event = {
        "type": "tool_execution_start",
        "toolCallId": "tc_2",
        "toolName": "bash",
        "args": "not-a-dict",
    }
    run = _parse(_lines(SESSION, event))
    assert len(run.tools) == 1
    assert run.tools[0].input == {}


def test_tool_execution_end_with_no_result_yields_empty_content():
    event = {
        "type": "tool_execution_end",
        "toolCallId": "tc_3",
        "toolName": "bash",
        # no "result" key
    }
    run = _parse(_lines(SESSION, event))
    tool_result_steps = [s for s in run.steps if s.type == StepType.TOOL_RESULT]
    assert len(tool_result_steps) == 1
    assert tool_result_steps[0].content == ""


def test_blank_lines_in_stream_are_skipped():
    stdout = "\n\n" + json.dumps(TEXT_MESSAGE_END) + "\n   \n"
    run = _parse(stdout)
    assert len(run.steps) == 1
    assert run.steps[0].type == StepType.TEXT


def test_tool_execution_end_with_scalar_result_is_stringified():
    event = {
        "type": "tool_execution_end",
        "toolCallId": "tc_4",
        "toolName": "calc",
        "result": 42,
    }
    run = _parse(_lines(SESSION, event))
    tool_result_steps = [s for s in run.steps if s.type == StepType.TOOL_RESULT]
    assert len(tool_result_steps) == 1
    assert tool_result_steps[0].content == "42"
