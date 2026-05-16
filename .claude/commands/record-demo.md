Record a tea demo, upload the GIF to catbox.moe, and open a draft PR.

Usage: /record-demo <demo-name>

All working files stay local (/tmp) — nothing is committed to the repo.
The only persistent artifact is the GIF URL on catbox.moe.

## Steps

1. **Check dependencies.** Verify `asciinema`, `agg`, and `gh` are on PATH.
   If any are missing, stop and tell the user:
   - asciinema: `pip install asciinema --break-system-packages`
   - agg: download binary from https://github.com/asciinema/agg/releases
   - gh: https://cli.github.com

2. **Understand what to demonstrate.** The user will describe the feature in
   the `/record-demo` invocation or in prior context. Ask if unclear.

3. **Verify the feature works** by doing a dry run of the key commands.
   If anything fails, stop and fix it first. The demo must show passing
   checks (✓ not ✗) when applicable.

4. **Write the shell script** at `/tmp/tea-demo-$ARGUMENTS.sh`. Rules:

   **Environment setup (hidden from viewer):**
   - `cd "$(git rev-parse --show-toplevel)"` at the top
   - Run all setup silently: venv activation, Docker readiness, cache warming.
     Redirect noisy output to `/dev/null`. The viewer should only see commands
     that are part of the story.

   **Demo commands (visible to viewer):**
   - Echo each command before running it: `echo "$ <command>"`
   - `sleep 1` before each command so the viewer can read the prompt
   - `sleep 5` after commands whose output should be read (cat, short results)
   - No extra sleep after long-running commands — the output provides pacing
   - **Prefix tea/harntest with `NO_SPINNER=1`** — the spinner emits output
     every 80ms, preventing agg from compressing idle time
   - A blank `echo ""` between sections for breathing room

   Example skeleton:
   ```bash
   #!/usr/bin/env bash
   set -e
   cd "$(git rev-parse --show-toplevel)"

   # ── silent setup ───────────────────────────────────────────────────────────
   source venv/bin/activate
   docker info >/dev/null 2>&1

   # ── demo ───────────────────────────────────────────────────────────────────
   echo "$ cat path/to/file.py"
   sleep 1
   cat path/to/file.py
   sleep 5

   echo ""
   echo "$ harntest path/to/test.py"
   sleep 1
   NO_SPINNER=1 harntest path/to/test.py
   ```

5. **Record and convert:**
   ```
   python scripts/record_demo.py $ARGUMENTS
   ```
   Reads `/tmp/tea-demo-$ARGUMENTS.sh`, writes cast and GIF to `/tmp/`.
   Prints the GIF path on stdout.

   **Upload to catbox.moe** (no credentials needed):
   ```
   python scripts/upload_gif.py /tmp/tea-demo-$ARGUMENTS.gif
   ```
   Prints the hosted URL on stdout. Copy it — you need it for the PR.

   Or pipe them together:
   ```
   python scripts/record_demo.py $ARGUMENTS | xargs python scripts/upload_gif.py
   ```

6. **Open a draft PR** using the hosted URL:
   ```
   gh pr create --draft \
     --title "<short description of the feature shown>" \
     --body "$(cat <<'EOF'
   ## Summary
   <bullet points>

   ## Demo

   ![Demo](<catbox-url>)

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   EOF
   )"
   ```
