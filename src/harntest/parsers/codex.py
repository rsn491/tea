from __future__ import annotations

import json

from harntest.models import AgentRun, Step, ToolCall


def parse(stdout: str) -> AgentRun:
    steps: list[Step] = []
    tools: list[ToolCall] = []

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type")

        if msg_type == "message":
            role = msg.get("role", "text")
            content = msg.get("content", "")
            if isinstance(content, str):
                steps.append(Step(type=role, content=content, raw=msg))
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "output_text":
                        steps.append(Step(type="text", content=block.get("text", ""), raw=block))

        elif msg_type == "function_call":
            name = msg.get("name", "")
            arguments = msg.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"raw": arguments}
            tc = ToolCall(
                name=name,
                input=arguments,
                tool_use_id=msg.get("call_id", ""),
            )
            tools.append(tc)
            steps.append(Step(type="tool_use", content=json.dumps(arguments), raw=msg))

        elif msg_type == "function_call_output":
            steps.append(Step(
                type="tool_result",
                content=str(msg.get("output", "")),
                raw=msg,
            ))

    return AgentRun(
        raw=stdout,
        steps=steps,
        tools=tools,
        skills=[],  # Codex has no skills concept
    )
