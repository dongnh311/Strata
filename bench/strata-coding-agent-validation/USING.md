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

## One conversation at a time: no parallel subagents

Strata keeps **one conversation warm** and serves one request at a time. Anything that sends it a *different*
conversation pushes yours out of the cache, and your next turn re-reads it from token 0 (64 s at 43K tokens, 108 s at
72K, about 5 min at 200K). Claude Code creates other conversations in three ways: **parallel subagents** (the `Agent` and
`Workflow` tools), a second session at the same time, and - in auto mode only - the safety classifier.

Measured on a real session (RTX 3060, 09:00-09:18, a 36K-72K-token conversation; the model had opened 3 parallel
subagents, which share a 21,226-token system prefix and arrive as several near-identical requests):

| | |
| :-- | :-- |
| Server busy | 17.6 min for 36 requests |
| Side-conversation requests (subagents) | 13 requests = 328 s |
| Main conversation re-read from scratch | 3 times = 234 s |
| **Avoidable** | **580 s = 55% of the server's busy time** |
| A normal warm turn of the main conversation | 21.8 s on average |

While the subagents run, the main conversation does not move at all (here no turn from 09:14 until they finished, with 5
requests queued). On a server that does one thing at a time, parallel subagents are slower than doing the same work in
the main conversation, where every follow-up turn is cached.

The launchers therefore start Claude Code with `--disallowedTools "Agent,Workflow"`, which removes both tools from
what the model is offered (checked: 23 tools become 21). The flag takes a list, so it goes **last** on the command line:
written before a prompt it would swallow it. Remove it if you want subagents anyway.

Auto mode is a separate way to hit the same wall, tested in the lab but not seen in the measured session above (that one
ran in bypass mode): for each action that needs approval Claude Code sends 5 or more requests with its own
"security monitor" system prompt (about 144,000 characters, no tools) to the same model. Bypass mode
(`--dangerously-skip-permissions`) and `acceptEdits` sent none for the same risky command. If you use auto mode with
Strata, expect each approval to cost a cold re-read.

## Images (screenshots)

The server reads images (`"images": true` in `/health`, "images on" at start): attach one in the web chat (reload the
page once; the paperclip says "Attach a text file or a picture"), or let Claude Code open one with its Read tool
(`Read shot.png`). Measured on the RTX 3060 PC with the Q2_K refusal model: a 1280x720 screenshot of code at 22 px was
quoted exactly (a comment, a TypeError message, `checkout.py:42`) and the model then explained the bug; a picture of
"MEN WALK ON MOON" with a red square and a blue circle was described correctly through the OpenAI and Anthropic APIs
and through Claude Code's Read.

It costs **4.3 s per new picture** (the same picture again is free) and about **1 GB of RAM** for the encoder
(`strata-vision.exe`, on the CPU with 4 threads, pictures scaled to ~300 tokens); the GPU is not touched, and text speed
did not change (a cold 17.5K-token prompt: prefill 705-717 tok/s, decode 43-46 tok/s, against 676-686 and 37-44 before).
The config's `vision` section points `model` at the Q2_0 original, not the unc48L file: llama.cpp cannot read the
trimmed Q2_K file (rows of 640 values) and the helper only needs the vocabulary and the embedding width.

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
