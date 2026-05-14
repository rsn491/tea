from harntest.agent import _AgentCatalog as Agent, RunBuilder
from harntest.agent.agent import Agent as AgentBase
from harntest.agent.claude_code import ClaudeCode
from harntest.agent.harness import Harness
from harntest.executor import DockerSpec, Executor, ExecutionSpec, RawResult
from harntest.executor.docker import DockerExecutor
from harntest.agent.agent_run import AgentRun, FileChange, FileDiff, Step, ToolCall
from harntest.checkers import check, check_diff_added, check_skill_used
from harntest.runner import TestRunner, iterations

__all__ = [
    "Agent",          # catalog — Agent.ClaudeCode unchanged
    "AgentBase",      # ABC for type hints
    "ClaudeCode",     # public name for the Claude agent
    "DockerExecutor",
    "Executor",
    "ExecutionSpec",
    "DockerSpec",
    "RawResult",
    "Harness",
    "RunBuilder",
    "AgentRun", "FileChange", "FileDiff", "Step", "ToolCall",
    "TestRunner", "iterations",
    "check", "check_diff_added", "check_skill_used",
]
