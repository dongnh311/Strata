# Using Strata as your coding model (Claude Code)

Validated GO — see `RESULT.md`. This is how to drive it day to day and how to keep it fast.

## Start it

1. Start the Strata server (once): run `run-unc48l-q2ktrim-refusal.bat` (serves `127.0.0.1:18080`, Tailscale
   `:8443`, refusal projection on at strength 1.0).
2. In your project, launch Claude Code against Strata:
   ```
   cd <your project>
   D:\GitHub\Strata\code-strata.bat
   ```
   `code-strata.bat` sets the endpoint, model, a separate Claude Code profile, and the three env vars that unlock
   the full 512K window; it passes any extra args through to `claude` (e.g. `code-strata -p "fix the failing test"`).
   It checks the server is up first and tells you if it is not.

Normal Claude Code permissions apply (it was not built to skip them). The profile lives at
`D:\GitHub\Strata-data\cc-strata`, separate from your real Claude Code, so histories don't mix.

## Keep it fast — the one thing that matters

The slow part is the **first cold load of a large context** (≈4 min at 156K tokens, ≈10 min at 312K, ≈16 min near
the top). Everything after that is quick: Strata caches the conversation prefix, so follow-up turns read only their
new tokens in 1–2 s and decode at ~37 tok/s. So:

- **Keep one Claude Code session open** and work in it. Don't quit and relaunch for each task — a relaunch loses the
  warm prefix and pays the cold load again. (Parked-conversation caching across sessions is off, and cannot be
  turned on here: physical RAM is already near full with the expert arena, ~3.5 GB free.)
- **Let Claude Code pull files in as it needs them** rather than pasting a whole huge repo up front. Reading files
  on demand spreads the prefill cost over turns and keeps the cache growing with what you actually touch.
- **Stay under ~475K tokens of your own content.** Through Claude Code the usable window is ~475K (it reserves
  output + system from the 524288 total) and it refuses "Prompt is too long" above that — a clean stop, nothing
  lost, but plan long sessions with that ceiling in mind.
- **One request at a time.** Strata serves serially, so Claude Code subagents that fan out in parallel queue rather
  than run together — they are not a speed win here.

## Good to know

- **Recall is reliable to at least 437K tokens** (tested 3/3 at 156K/312K/437K) — using facts from early in a big
  context is solid, well past the model's 262K trained length.
- **Uncensored.** The refusal-projection vector is on; the model declines far less. Read shell commands it proposes
  before approving, as you would for any agent.
- To turn the uncensoring off or change its strength, use the web app's Sampling drawer ("Bỏ kiểm duyệt
  (Uncensored)" + the strength slider) at `http://127.0.0.1:18080`.
