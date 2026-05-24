from tea import Agents, check_diff_added

_agents = Agents(skills_dir="skills")


def test_add_minus_operation_codex():
    run = (
        _agents.Codex.with_subscription()
        .prompt("Add 'minus' operation support to the calculator")
        .workdir("examples/demo_calculator")
        .run()
    )

    check_diff_added(run, "calculator.py", "minus")
    check_diff_added(run, "test_calculator.py", "test_minus")
