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

## From another machine (Claude Code or Codex over Tailscale / LAN)

You can run the agent on a different PC and use this one as the server. The server now binds
`0.0.0.0` and **requires an API key** (AGENTS.md forbids exposing it beyond loopback without one) —
`"host"` and `"api_key"` are set in `strata-unc48l-q2ktrim-refusal.json`.

- **Tailscale (recommended):** endpoint `https://pc-dik-win.tail1b3f7b.ts.net:8443` (real TLS cert, works
  anywhere on the tailnet, no firewall change — `tailscale serve` already proxies it to `127.0.0.1:18080`).
- **LAN:** endpoint `http://172.16.14.244:18080`; run `allow-lan-firewall.bat` on this PC once to open TCP 18080.

Ready-to-copy client launchers (Claude Code **and** Codex, Windows `.bat` + `.sh`) are in `remote-client/`
with their own `README.md`; they carry the key and the endpoints, so that folder is git-ignored. Codex uses
Strata's OpenAI chat-completions API (`wire_api = "chat"`; the Responses API is not supported). Both protocols
were verified end-to-end against the Tailscale endpoint with the key. The local launcher `code-strata.bat` was
updated to send the key too.

## Don't use Claude Code's auto mode with Strata

Auto mode checks every action that needs approval with a **separate request to the same model**: its own system prompt
("security monitor for autonomous AI coding agents", ~144,000 characters), no tools, 5 or more calls per action. Strata
keeps one conversation warm at a time, so each of those calls pushes your real conversation out of the cache, and the
next turn re-reads it from token 0. Measured on a real session (RTX 3060, 09:00-09:18, a 36K-72K-token conversation):

| | |
| :-- | :-- |
| Server busy | 17.6 min for 36 requests |
| Classifier-like side requests | 13 requests = 328 s |
| Main conversation re-read from scratch | 3 times = 234 s (64 s at 43K tokens, 108 s at 72K) |
| **Avoidable** | **580 s = 55% of the server's busy time** |
| A normal warm turn of the main conversation | 21.8 s on average |

One approval of a single action cost about 4.4 minutes (146 s of classifier calls + a 118 s re-read). The same classifier
timing out is what shows as "the safety classifier is temporarily down" and blocks every Bash and Write.

The launchers start Claude Code with `--permission-mode acceptEdits` (file edits go through; shell commands ask you,
which costs your attention but no server time). Pick the mode that fits:
- `acceptEdits` (the launcher default): you approve shell commands; choose "don't ask again" for the ones you trust.
- `--dangerously-skip-permissions`: no prompts at all (see the notes below on what that risks with this model).
- Avoid `--permission-mode auto`, and pressing Shift+Tab into it.

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

- **Web search works.** The launchers send `X-Strata-MCP: 1` (`ANTHROPIC_CUSTOM_HEADERS` for Claude Code,
  `http_headers` for Codex). The server then runs its MCP tools (the AI-Gateway's `web_search`, `fetch_url`, ...) itself.
  Claude Code's own WebSearch tool goes through them, and the search shows as a thinking line. Tested: "latest stable
  Rust" was answered from a real search with the source URL.
- **Recall is reliable to at least 437K tokens** (tested 3/3 at 156K/312K/437K) — using facts from early in a big
  context is solid, well past the model's 262K trained length.
- **Uncensored.** The refusal-projection vector is on; the model declines far less. Read shell commands it proposes
  before approving, as you would for any agent.
- To turn the uncensoring off or change its strength, use the web app's Sampling drawer ("Bỏ kiểm duyệt
  (Uncensored)" + the strength slider) at `http://127.0.0.1:18080`.
