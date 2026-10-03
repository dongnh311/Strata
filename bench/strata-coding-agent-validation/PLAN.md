# Validation plan: Strata as a long-context coding agent (via Claude Code)

**Goal.** Decide go/no-go on using the local Strata model as the *main* coding model, driven by Claude Code,
over long context (up to 512K). One-time validation producing a report with per-dimension results, the depth
where quality starts to fall, the weak spots, and a recommendation.

**Written** 2026-10-03. The numbers below marked *target* are the bar to clear, not measurements; every
measured number in the report must say what it was measured on (machine, config, context depth, run count).

## System under test

| | |
| :--- | :--- |
| Model | `qwen38-orca-q2k-refusal` — Qwen3.8-Flash-Next OrcaUncensored, trimmed Q2_K down experts, refusal-projection control vector at scale 1.0 |
| Config | `strata-unc48l-q2ktrim-refusal.json` (engine `D:\GitHub\Strata-data\build-wc\strata.exe`, 0.1.38 + runtime cvec scale) |
| Context | 524288 tokens, YaRN ×2 (trained length 262144, so >262K is extrapolated) |
| Endpoint | `POST http://127.0.0.1:18080/v1/messages` (Anthropic), also `/v1/chat/completions` (OpenAI); Tailscale `https://pc-dik-win.tail1b3f7b.ts.net:8443` |
| Measured so far | decode ~37 tok/s (480-token gen, warm cache); prefill ~560 tok/s at 20K; expert cache hit ~69% |
| GPU | RTX 3060 12 GB |

**Constraints that shape the tests** (verified in `serve/server.py`):
- **Serial FIFO** — the engine serves one request at a time; Claude Code subagents that fan out in parallel are
  queued, not run concurrently. Measure wall-clock with this in mind; a parallel step is the sum of its parts.
- **Conversation cache (resume)** — within a session the shared prefix is reused, so only new tokens are read
  each turn. The first large prompt pays full prefill; follow-ups should be cheap. The tests must separate
  cold-prompt cost from warm-turn cost.
- **`strip_cjk` on** — stray Chinese characters are removed from the answer. Watch for it eating legitimate
  content in code (e.g. a Chinese string literal or comment).
- **Refusal projection on (scale 1.0)** — the model is uncensored; not a coding concern, but note any case where
  it over-complies in a way that produces unsafe shell commands without a caveat.

## Dimension 0 — Integration smoke test (gate; run first)

The largest unknown: Claude Code's tool-use protocol and system prompt are tuned for Claude models; Strata is a
Qwen fine-tune serving the Anthropic API. If the basic loop does not hold, stop here and report.

**Setup** (isolated, does not touch the user's real Claude Code):
```sh
export ANTHROPIC_BASE_URL=http://127.0.0.1:18080
export ANTHROPIC_AUTH_TOKEN=local-strata          # Strata has no api_key set, so any token passes; the var must exist
export ANTHROPIC_MODEL=qwen38-orca-q2k-refusal
export CLAUDE_CONFIG_DIR="$PWD/cc-profile"          # a throwaway config dir, so settings/history stay separate
```

**Checks (each a `claude -p` headless run in a scratch git repo):**
1. No tools: `claude -p "reply with exactly: OK"` → returns, streams, no protocol error.
2. One tool: "read README.md and tell me its first heading" → one valid `tool_use` (Read), correct `tool_result`
   round-trip, a sensible answer.
3. One edit + verify: "add a function `add(a,b)` to calc.py and run it" → Read/Write/Bash calls parse, the file
   is written, Bash runs, the loop terminates.

**Gate:** all three complete with valid tool-call JSON and clean termination. If tool-call parsing is malformed or
the loop never ends, record the exact failure and stop — the rest of the matrix is moot until integration holds.

## Dimension 1 — Long-context recall (256K–512K)

**1a. Needle-in-haystack in a codebase context.** Build filler context from real source (concatenated repo files)
to target sizes **128K, 256K, 384K, 512K** tokens. Insert one unique, verifiable fact at depth **10%, 50%, 90%**
(e.g. a function `secret_token_xyz()` returning a specific constant, or a specific config value). Ask Claude Code
a question only answerable from the needle. Score: correct / wrong / refused-to-find, per (size × depth) cell.

**1b. Cross-file reference in a real repo.** A ~200–400K-token repo loaded into the session; ask for a change that
requires a detail defined in an early file (e.g. "update every caller of `oldName` to `newName`" where the
definition is near the top of the context). Score: did it find and use the early information, or hallucinate.

**Report:** a size×depth grid of recall, and the depth where recall drops below 50% (expected near/after the
262K YaRN boundary). *Target:* ≥90% up to 128K, ≥70% at 256K; document the fall-off beyond.

## Dimension 2 — Agentic tool use

Multi-step coding tasks driven through Claude Code's own tools (Read/Edit/Bash/Grep), 5–8 tasks of rising length,
e.g. "find and fix the failing test", "add a flag across 3 files and update its help text", "trace a bug from a
stack trace to its cause and fix it". For each, measure:
- **Tool-call validity** — fraction of `tool_use` blocks that parse and name a real tool with usable args.
- **Turns to completion** vs a reasonable minimum; whether it loops or goes off-track.
- **Deep-session stability** — does tool-call validity degrade as the session grows past 128K/256K.

*Target:* ≥95% tool-call validity; completes ≥80% of tasks to a correct end without manual nudging.

## Dimension 3 — Code correctness

A fixed set of **10–15 real tasks** across the languages the user works in — **Rust, C++, Kotlin** and others —
each with an **automated check** (unit test passes, script output matches, or build succeeds). Spread the set so
each of the main languages has at least a couple of tasks, since compiled-language build/type errors are a
different failure mode from a script that merely runs. Run each headless (`claude -p`) against Strata,
score pass/fail on the check — not on the prose. Run 2–3 of them a second time to see run-to-run variance.
**Calibration:** run the same 2–3 tasks on the user's normal Claude Code model and compare, so a Strata failure
is read against the task's difficulty, not in a vacuum.

*Target:* ≥70% of tasks pass their check; the report lists which kinds fail (language, task shape).

## Dimension 4 — Speed at depth

For fresh prompts at **32K / 128K / 256K / 512K** tokens, measure:
- **Prefill (prompt-reading) tok/s** and, more importantly, **wall-clock to first output token** on a *cold*
  prompt at each depth — this is what a user feels when a big file or repo first enters the session.
- **Warm-turn cost** — after the context is cached, the wall-clock of a follow-up turn that adds a small amount
  (the realistic steady state of an agent session).
- **Decode tok/s** at each depth (does it hold near the ~37 tok/s measured at short context).

*Target (to decide usability, not a pass/fail on the model):* a cold 256K prompt reaches first token within a
tolerable wait for interactive use; warm turns stay well under that. Flag any depth where a single turn is too
slow to work with, and note it against the user's real depth (they report sessions reach 256K–512K).

## Scoring and the go/no-go report

The report (`RESULT.md` beside this plan) states, per dimension: the method, the measured numbers (with
conditions), pass/fail against the targets above, and the **degradation depth**. It ends with a recommendation:
- use Strata as the main coding model, yes/no, and **up to what context depth**;
- the weak spots to avoid (e.g. "recall unreliable past 300K", "struggles with multi-file refactors");
- any config change worth trying (e.g. capping the working context below the YaRN boundary if recall falls off).

**Go/no-go bar (proposed; adjust before running):** Dimension 0 must pass. Then a "go" needs recall ≥70% at the
user's typical depth, tool validity ≥95%, correctness ≥70%, and no depth in normal use that is unusably slow.

## Harness layout

```
bench/strata-coding-agent-validation/
  PLAN.md                 this file
  cc-profile/             throwaway CLAUDE_CONFIG_DIR (gitignored)
  env.sh                  the ANTHROPIC_* exports above
  make_context.py         build filler + insert needles to a target token size (uses the tokenizer in the pack)
  tasks/                  the correctness task set: each a prompt + a check script
  run_smoke.sh            Dimension 0
  run_recall.py           Dimensions 1 (size×depth grid), writes recall.json
  run_agentic.py          Dimension 2, drives claude -p, logs tool-call validity + turns
  run_correctness.py      Dimension 3, runs tasks/, scores checks
  run_speed.py            Dimension 4, times cold/warm turns at each depth (reads engine timings from the log)
  RESULT.md               the go/no-go report (written at the end)
```

Each runner drives Claude Code headless (`claude -p "<task>" --output-format json`) with the isolated profile, and
reads Strata's per-request timings from `strata-unc48l-q2ktrim-refusal.log` (`prompt ... read in ... ms`,
`... generated in ... ms`, `drafts accepted`, `decode expert cache hit rate`) for the speed and cache numbers.

## Risks and notes

- **Integration may simply not hold** (Dimension 0). That is itself a finding; capture the exact protocol failure.
- **Serial FIFO**: if a task makes Claude Code fan out subagents, they queue — time it as serial, and note that
  parallel agent patterns are not a speed win here.
- **Engine is the local build** (`build-wc\strata.exe`). If it is ever replaced, re-run Dimension 0 at minimum.
- **Context cache invalidation**: changing the refusal-projection strength (the web slider) drops the cache, so
  keep the strength fixed (1.0) through a run or the warm-turn numbers will be wrong.
- **One machine, one model, one quant** — the report's numbers are for this exact setup; do not generalize.
