Record a harntest demo and produce a GIF for embedding in PR descriptions.

Usage: /record-demo <demo-name>

The demo name refers to a file in `.claude/demos/<demo-name>.md` which describes
what the demo should show. You will translate that description into a shell script,
record it with asciinema, and convert it to a GIF.

## Steps

1. **Check dependencies.** Verify `asciinema` and `agg` are on PATH. If either is
   missing, stop and tell the user:
   - asciinema: `pip install asciinema --break-system-packages`
   - agg: download binary from https://github.com/asciinema/agg/releases

2. **Read the demo spec** at `.claude/demos/$ARGUMENTS.md`. Understand what it
   wants to demonstrate and what setup is required.

3. **Verify the feature works** by doing a dry run of the key commands before
   recording. If anything fails, stop and fix it — a demo showing failures is
   not useful.

4. **Write a shell script** at `/tmp/harntest-demo-$ARGUMENTS.sh` that implements
   the demo. The script should:
   - Include any setup steps described in the spec (create files, activate venv, etc.)
   - Run the commands that show the feature working, prefixed with `NO_SPINNER=1` to
     suppress the animated spinner (it emits output every 80ms, preventing `agg` from
     compressing idle time — without it, LLM wait time shows in full)
   - Use `sleep 1` before running each command so the viewer can read the prompt
   - Use `sleep 5` after commands that produce output worth reading (cat, short results)
   - Use no extra sleep after long-running commands (the output itself provides pacing)
   - Print a blank line between sections for visual breathing room
   - Work from the repo root directory

5. **Record** the script with a wide terminal so output isn't truncated:
   ```
   asciinema rec --overwrite --cols 220 --rows 50 -c "bash /tmp/harntest-demo-$ARGUMENTS.sh" docs/demos/$ARGUMENTS.cast
   ```

6. **Convert** to GIF, compressing idle time so long LLM calls don't inflate
   the GIF duration, and holding the final frame long enough to read:
   ```
   agg --font-size 14 --cols 220 --idle-time-limit 1 --last-frame-duration 10 docs/demos/$ARGUMENTS.cast docs/demos/$ARGUMENTS.gif
   ```

7. **Output** the ready-to-paste markdown snippet:
   ```
   ![Demo](docs/demos/$ARGUMENTS.gif)
   ```
   And confirm the GIF was created with its file size.
