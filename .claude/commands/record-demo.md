Record a harntest demo, upload the GIF to GitHub, and open a draft PR.

Usage: /record-demo <demo-name>

The demo name refers to a spec file at `docs/demos/<demo-name>.md` that describes
what the demo should show. You will translate that into a shell script, record it,
and open a draft PR with the GIF embedded.

## Steps

1. **Check dependencies.** Verify `asciinema`, `agg`, and `gh` are on PATH.
   If any are missing, stop and tell the user:
   - asciinema: `pip install asciinema --break-system-packages`
   - agg: download binary from https://github.com/asciinema/agg/releases
   - gh: https://cli.github.com

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
   docker info >/dev/null 2>&1

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

5. **Record and convert:**
   ```
   python scripts/record_demo.py $ARGUMENTS
   ```
   Progress goes to stderr; the GIF path is printed on stdout.

   **Upload to GitHub** (pipe or run separately):
   ```
   python scripts/upload_gif.py docs/demos/$ARGUMENTS.gif
   ```
   Uploads to a persistent `demo-assets` draft release (created once, reused
   forever; re-uploading the same name replaces the asset). Prints the hosted
   URL on stdout. Copy that URL — you need it for the PR.

6. **Commit** the cast file, GIF, and shell script:
   ```
   git add docs/demos/$ARGUMENTS.cast docs/demos/$ARGUMENTS.gif docs/demos/$ARGUMENTS.sh
   git commit -m "Add $ARGUMENTS demo recording"
   git push
   ```

7. **Open a draft PR** using the hosted URL from step 5:
   ```
   gh pr create --draft \
     --title "<short description of the feature shown>" \
     --body "$(cat <<'EOF'
   ## Summary
   <bullet points describing the change>

   ## Demo

   ![Demo](<hosted-gif-url-from-step-5>)

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   EOF
   )"
   ```
