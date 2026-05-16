Record a harntest demo and produce a GIF for embedding in PR descriptions.

Usage: /record-demo <demo-name>

The demo name refers to a spec file at `docs/demos/<demo-name>.md` that describes
what the demo should show. You will translate that into a shell script, then run
the deterministic recorder.

## Steps

1. **Check dependencies.** Verify `asciinema` and `agg` are on PATH. If either is
   missing, stop and tell the user:
   - asciinema: `pip install asciinema --break-system-packages`
   - agg: download binary from https://github.com/asciinema/agg/releases

2. **Read the demo spec** at `docs/demos/$ARGUMENTS.md`. Understand what it wants
   to demonstrate and what setup is required.

3. **Verify the feature works** by doing a dry run of the key commands before
   recording. If anything fails, stop and fix it — a demo showing failures is
   not useful. The demo must show passing checks (✓ not ✗) when applicable.

4. **Write the shell script** at `docs/demos/$ARGUMENTS.sh`. Rules:

   **Environment setup (hidden from viewer):**
   - `cd "$(git rev-parse --show-toplevel)"` at the top so it works from anywhere
   - Run all environment setup silently before the first echoed command: venv
     activation, Docker readiness checks, pre-warming caches, etc. Redirect
     noisy output to `/dev/null` if needed. The viewer should see only the
     commands that are part of the story, not scaffolding.

   **Demo commands (visible to viewer):**
   - Echo each command before running it: `echo "$ <command>"`
   - `sleep 1` before each command so the viewer can read the prompt
   - `sleep 5` after commands whose output the viewer should read (cat, short results)
   - No extra sleep after long-running commands — the output provides pacing
   - **Prefix harntest with `NO_SPINNER=1`** — the spinner emits output every 80ms
     and prevents agg from compressing idle time, so LLM wait times show in full
   - A blank `echo ""` between sections for visual breathing room

   Example skeleton:
   ```bash
   #!/usr/bin/env bash
   set -e
   cd "$(git rev-parse --show-toplevel)"

   # ── silent setup — not part of the story ──────────────────────────────────
   source venv/bin/activate
   docker info >/dev/null 2>&1  # ensure Docker is ready before recording starts

   # ── demo ──────────────────────────────────────────────────────────────────
   echo "$ cat path/to/file.py"
   sleep 1
   cat path/to/file.py
   sleep 5

   echo ""
   echo "$ harntest path/to/test.py"
   sleep 1
   NO_SPINNER=1 harntest path/to/test.py
   ```

5. **Record and convert** using the deterministic recorder:
   ```
   python scripts/record_demo.py $ARGUMENTS
   ```
   This records with asciinema (220×50), converts with agg (idle-time-limit 1s,
   last-frame 10s), and prints the markdown embed snippet.

6. **Output** the snippet printed by the script:
   ```
   ![Demo](docs/demos/$ARGUMENTS.gif)
   ```
   And report the file size.
