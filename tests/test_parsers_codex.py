import json
from harntest.parsers.codex import parse

MSG_ASSISTANT = {"type": "message", "role": "assistant", "content": "I will help."}
MSG_OUTPUT_TEXT = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done"}]}
FUNC_CALL = {"type": "function_call", "name": "shell", "arguments": {"command": "ls"}, "call_id": "call_1"}
FUNC_CALL_STR_ARGS = {"type": "function_call", "name": "shell", "arguments": '{"command": "pwd"}', "call_id": "call_2"}
FUNC_OUTPUT = {"type": "function_call_output", "call_id": "call_1", "output": "file.txt"}


def _lines(*msgs) -> str:
    return "\n".join(json.dumps(m) for m in msgs)


def test_message_string_content():
    run = parse(_lines(MSG_ASSISTANT))
    assert len(run.steps) == 1
    assert run.steps[0].content == "I will help."
    assert run.steps[0].type == "assistant"


def test_message_output_text_block():
    run = parse(_lines(MSG_OUTPUT_TEXT))
    assert len(run.steps) == 1
    assert run.steps[0].content == "Done"
    assert run.steps[0].type == "text"


def test_function_call():
    run = parse(_lines(FUNC_CALL))
    assert len(run.tools) == 1
    assert run.tools[0].name == "shell"
    assert run.tools[0].input == {"command": "ls"}
    assert run.tools[0].tool_use_id == "call_1"
    assert run.steps[0].type == "tool_use"


def test_function_call_string_args_parsed():
    run = parse(_lines(FUNC_CALL_STR_ARGS))
    assert run.tools[0].input == {"command": "pwd"}


def test_function_call_output():
    run = parse(_lines(FUNC_CALL, FUNC_OUTPUT))
    tr = [s for s in run.steps if s.type == "tool_result"]
    assert len(tr) == 1
    assert tr[0].content == "file.txt"


def test_skills_always_empty():
    run = parse(_lines(FUNC_CALL))
    assert run.skills == []


def test_raw_is_full_stdout():
    stdout = _lines(MSG_ASSISTANT, FUNC_CALL)
    run = parse(stdout)
    assert run.raw == stdout


def test_malformed_lines_skipped():
    stdout = "not json\n" + json.dumps(MSG_ASSISTANT)
    run = parse(stdout)
    assert len(run.steps) == 1
