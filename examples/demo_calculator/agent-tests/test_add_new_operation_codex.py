from tea import Agents, check_diff_added


def test_add_minus_operation_codex():
    run = (
        Agents.Codex.with_api_key()
        .prompt("Add 'minus' operation support to the calculator")
        .workdir("examples/demo_calculator")
        .run()
    )

    check_diff_added(run, "calculator.py", "minus")
    check_diff_added(run, "test_calculator.py", "test_minus")
