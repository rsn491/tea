from tea import Agents, check_diff_added, check_skill_used
from tea.runner import iterations

# Skills live in examples/demo_calculator/skills/. Tea has no default discovery
# path, so we wire it once at suite scope via the Agents factory.
_agents = Agents(skills_dir="skills")


@iterations(2)
def test_add_minus_operation():
    run = (
        _agents.ClaudeCode.prompt("Add 'minus' operation support to the calculator")
        .workdir("examples/demo_calculator")
        .run()
    )

    check_skill_used(run, "add-new-operation")
    check_diff_added(run, "calculator.py", "minus")
    check_diff_added(run, "test_calculator.py", "test_minus")
    check_diff_added(run, "README.md", "minus")


def test_add_multiply_operation():
    run = (
        _agents.ClaudeCode.prompt("Add 'multiply' operation support to the calculator")
        .workdir("examples/demo_calculator")
        .run()
    )

    check_skill_used(run, "add-new-operation")
    check_diff_added(run, "calculator.py", "multiply")
    check_diff_added(run, "test_calculator.py", "test_multiply")
    check_diff_added(run, "README.md", "multiply")
