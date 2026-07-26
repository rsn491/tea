# Changelog

## Unreleased

### Harness-specific model configs

`ModelConfig` was a three-field struct whose fields meant different things per
harness — Claude Code and Codex silently ignored `api_key_env` and `base_url`.
Configs are now harness-specific.

```python
# Claude Code and Codex take a plain model string
Agents.ClaudeCode.with_model("claude-opus-4-7").prompt("task").run()
Agents.Codex.with_model("gpt-5.3-codex").prompt("task").run()

# Pi takes a PiConfig, where api_key_env / base_url actually mean something
Agents.Pi.with_model(PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")).prompt("task").run()
```

### Executor-agnostic execution specs

`build_spec()` returned a `DockerSpec`, so every agent set `image`, `user`,
`extra_hosts` — Docker knobs — in agent code. Agents now return a plain
`ExecutionSpec` and declare *what they need* via `ExecutionRequirements`;
`DockerExecutor` translates those into Docker primitives. The static per-agent
Docker knowledge (image, dockerfile, user) moved into a `DockerProfile` supplied
to `DockerExecutor` at construction, passed as a callable so the CLI version
probe stays lazy.

The split is between *what the command needs* and *how the container is built*.
Process environment the CLI itself depends on (`HOME`, `NPM_CONFIG_PREFIX`,
`PI_OFFLINE`) stays in `ExecutionSpec.env`, so a spec runs correctly under any
executor; only image-level knowledge lives in the profile. `WORKDIR_MOUNT`
(`/workspace`) is likewise part of the executor contract rather than a
`DockerExecutor` private — agents build absolute skill paths against it, so
every executor must honour it.

Agent and image are wired together in exactly one place per agent —
`ClaudeCodeHarness.docker()` / `CodexHarness.docker()` / `PiHarness.with_model()`.
Each profile factory takes its agent (`claude_docker_profile(agent)`) and reads
the image tag from `agent.version()`, so the version an agent reports and the
image that runs cannot drift apart, and pairing a factory with a foreign agent
is a type error.

`with_model()` / `with_api_key()` rebuild a `DockerExecutor` around the new
agent but carry any other executor through untouched — selecting a model no
longer drags a custom executor back into Docker.

### Public API changes

| Symbol | Change |
|--------|--------|
| `ModelConfig` | **Removed** — use `PiConfig` (Pi) or `with_model(str)` (Claude Code, Codex) |
| `PiConfig` | **Added** — `PiConfig(model, api_key_env=None, base_url=None)`, exported from `tea` and `tea.agent` |
| `ClaudeCodeHarness.with_model` / `CodexHarness.with_model` | **Added** — take a model string; return the concrete harness type, so they compose with `with_api_key()` |
| `ClaudeCodeHarness.docker` / `CodexHarness.docker` | **Added** — pair an agent with the Docker image built for it |
| `DockerSpec` | **Removed** |
| `ExecutionRequirements` | **Added** — `ExecutionRequirements(host_network_access=False, extra_mounts={})` |
| `ExecutionSpec` | **Gains** `setup_command` and `requirements` |
| `DockerProfile` | **Added** — `DockerProfile(image, dockerfile=None, user=None, env_overrides={})`; importable from `tea` or `tea.executor.docker_executor`, *not* from `tea.executor` |
| `WORKDIR_MOUNT` | **Added** — `"/workspace"`, the path every executor must expose the workdir at; exported from `tea` and `tea.executor` |
| `claude_docker_profile` / `codex_docker_profile` / `pi_docker_profile` | **Added** — each takes its agent and derives the image tag from `agent.version()` |
| `DockerExecutor()` | **Requires a profile** — `DockerExecutor(profile, docker=None)` |

Migration for low-level callers:

```python
# before
DockerExecutor().run(DockerSpec(command="...", image="node:22", user="node"), workdir)
# after
DockerExecutor(DockerProfile(image="node:22", user="node")).run(ExecutionSpec(command="..."), workdir)
```

There is no deprecation shim: `ModelConfig`, `DockerSpec`, and no-arg
`DockerExecutor()` are gone outright.
