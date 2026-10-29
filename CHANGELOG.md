# Changelog

## Unreleased

### Colima runtime

`tea --runtime colima` runs agents on a running [Colima](https://github.com/abiosoft/colima)
instance instead of the default Docker socket — a faster, free alternative to
Docker Desktop on macOS. The socket is resolved via `colima status --json`.

### Harness-specific model configs

`ModelConfig` was a three-field struct whose fields meant different things per
harness — Claude Code silently ignored `api_key_env` and `base_url`.
Configs are now harness-specific.

```python
# Claude Code takes a plain model string
Agents.ClaudeCode.with_model("claude-opus-4-7").prompt("task").run()

# Pi takes a PiConfig, where api_key_env / base_url actually mean something
Agents.Pi.with_model(PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")).prompt("task").run()
```

### Executor-agnostic execution specs

`build_spec()` returned a `DockerSpec`, so every agent set `image`, `user`,
`extra_hosts` — Docker knobs — in agent code. Agents now return a plain
`ExecutionSpec` and declare *what they need* via `ExecutionRequirements`;
`DockerExecutor` translates those into Docker primitives. The static per-agent
Docker knowledge (image, dockerfile, user, base env) moved into a
`DockerProfile` supplied to `DockerExecutor` at construction, passed as a
callable so the CLI version probe stays lazy.

Agent and image are wired together in exactly one place per agent —
`ClaudeCodeHarness.docker()` / `PiHarness.with_model()`.
Prefer those over constructing `Harness(agent, DockerExecutor(profile))` by
hand, which type-checks even when the agent and image do not match.

### Public API changes

| Symbol | Change |
|--------|--------|
| `ModelConfig` | **Removed** — use `PiConfig` (Pi) or `with_model(str)` (Claude Code) |
| `PiConfig` | **Added** — `PiConfig(model, api_key_env=None, base_url=None)`, exported from `tea` and `tea.agent` |
| `ClaudeCodeHarness.with_model` | **Added** — takes a model string; returns the concrete harness type, so it composes with `with_api_key()` |
| `ClaudeCodeHarness.docker` | **Added** — pairs an agent with the Docker image built for it |
| `DockerSpec` | **Removed** |
| `ExecutionRequirements` | **Added** — `ExecutionRequirements(host_network_access=False, extra_mounts={})` |
| `ExecutionSpec` | **Gains** `setup_command` and `requirements` |
| `DockerProfile` | **Added** — `DockerProfile(image, dockerfile=None, user=None, env_overrides={})`; importable from `tea` or `tea.executor.docker_executor`, *not* from `tea.executor` |
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
