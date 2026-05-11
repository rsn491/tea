from harntest import Agent

def test_add_minus_operation():
    result = (
        Agent.ClaudeCode
            .prompt("Add 'minus' operation support to the calculator")
            .workdir("examples/demo_calculator")
            .run()
    )

    assert "add-new-operation" in result.skills
    assert "minus" in result.diff("calculator.py")
    assert "test_minus" in result.diff("test_calculator.py")
    assert "minus" in result.diff("README.md")