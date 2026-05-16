#!/usr/bin/env bash
# Demo: running a harntest agent test
# Generated from docs/demos/calculator-test.md
set -e
cd "$(git rev-parse --show-toplevel)"
source venv/bin/activate

echo "$ cat examples/demo_calculator/agent-tests/test_add_new_operation.py"
sleep 1
cat examples/demo_calculator/agent-tests/test_add_new_operation.py
sleep 5

echo ""
echo "$ harntest examples/demo_calculator/agent-tests/test_add_new_operation.py"
sleep 1
NO_SPINNER=1 harntest examples/demo_calculator/agent-tests/test_add_new_operation.py
