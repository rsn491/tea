from __future__ import annotations

import json

from harntest.models import AgentRun, Step, ToolCall

def _skill_from_tool(tc: ToolCall) -> str | None:
    if tc.name == "Skill":
        skill = tc.input.get("skill")
        if isinstance(skill, str) and skill:
            return skill
    if tc.name == "Bash":
        cmd = tc.input.get("command", "")
        if isinstance(cmd, str) and cmd.startswith("/"):
            return cmd.split()[0]
    return None


def parse(stdout: str) -> AgentRun:
    steps: list[Step] = []
    tools: list[ToolCall] = []
    skills: list[str] = []
    session_id: str | None = None
    cost_usd: float | None = None

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type")

        if msg_type == "system" and msg.get("subtype") == "init":
            session_id = msg.get("session_id")

        elif msg_type == "assistant":
            for block in msg.get("message", {}).get("content", []):
                block_type = block.get("type")
                if block_type == "text":
                    steps.append(Step(type="text", content=block["text"], raw=block))
                elif block_type == "tool_use":
                    tc = ToolCall(
                        name=block["name"],
                        input=block.get("input", {}),
                        tool_use_id=block["id"],
                    )
                    tools.append(tc)
                    steps.append(Step(
                        type="tool_use",
                        content=json.dumps(block.get("input", {})),
                        raw=block,
                    ))
                    skill = _skill_from_tool(tc)
                    if skill and skill not in skills:
                        skills.append(skill)

        elif msg_type == "tool_result":
            content = msg.get("content", "")
            if isinstance(content, list):
                text = " ".join(
                    b.get("text", "") for b in content if b.get("type") == "text"
                )
            else:
                text = str(content)
            steps.append(Step(type="tool_result", content=text, raw=msg))

        elif msg_type == "result" and msg.get("subtype") == "success":
            cost_usd = msg.get("total_cost_usd")
            if not session_id:
                session_id = msg.get("session_id")

    return AgentRun(
        raw=stdout,
        steps=steps,
        tools=tools,
        skills=skills,
        session_id=session_id,
        cost_usd=cost_usd,
    )
