from tea import (
    Agents,
    check_diff_added,
    check_file_changed,
    check_run_score,
    check_skill_used,
)
from tea.runner import iterations


@iterations(1)
def test_add_minus_operation():
    run = (
        Agents.ClaudeCode.prompt("Add 'minus' operation support to the calculator")
        .workdir("examples/demo_calculator")
        .run()
    )

    check_diff_added(run, "calculator.py", "def minus")
    check_diff_added(run, "test_calculator.py", "def test_minus")
    check_file_changed(run, "README.md")
    check_skill_used(run, "add-new-operation")
    check_run_score(
        run,
        (
            "Does this diff correctly implement a subtraction operation "
            "without breaking the existing structure? "
            "Score 1.0 if the implementation is clean and complete, "
            "0.5 if it works but has style issues, "
            "0.0 if it is broken or missing."
        ),
        min_score=0.7,
    )


def test_add_multiply_operation():
    run = (
        Agents.ClaudeCode.prompt("Add 'multiply' operation support to the calculator")
        .workdir("examples/demo_calculator")
        .run()
    )

    check_skill_used(run, "add-new-operation")
    check_diff_added(run, "calculator.py", "multiply")
    check_diff_added(run, "test_calculator.py", "test_multiply")
    check_diff_added(run, "README.md", "multiply")
