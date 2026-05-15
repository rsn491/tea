# Demo: running a harntest agent test

Show harntest running an agent test against the demo calculator project.
The goal is to show the full loop: a test file, running it, and seeing the results.

## What to demonstrate

1. Show the test file so the viewer understands what's being tested:
   ```
   cat examples/demo_calculator/agent-tests/test_add_new_operation.py
   ```

2. Run the test (one iteration so it's fast enough for a demo):
   ```
   harntest examples/demo_calculator/agent-tests/test_add_new_operation.py
   ```

3. The output should show the harntest banner, test progress, and pass/fail results.

## Setup

- Working directory: repo root
- Python venv must be activated: `source venv/bin/activate`
- Docker must be running (the test runs the agent inside Docker)
- Auth: `~/.claude` credentials are used automatically

## Notes

- The test actually runs the agent — this is a real run, not staged output.
- It will take 1-3 minutes; that's expected and fine for the recording.
- **The demo must show passing checks.** Before recording, verify the test passes
  by running it once manually. Only record once you see ✓ results, not ✗.
