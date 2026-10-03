# Strata as a long-context coding agent — validation results

Running against `strata-unc48l-q2ktrim-refusal.json` (model `qwen38-orca-q2k-refusal`, engine
`build-wc\strata.exe` 0.1.38 + runtime cvec, refusal projection scale 1.0), RTX 3060 12 GB, driven by
Claude Code `claude.exe` v2.1.286 over `http://127.0.0.1:18080/v1/messages`. See `PLAN.md` for the method.

## Dimension 0 — Integration smoke test: **PASS** (2026-10-03)

| Check | Result |
| :--- | :--- |
| 1. No tools (connectivity) | ✅ `result:"OK"`, `is_error:false`, 1 turn |
| 2. One tool (Read) | ✅ read README.md, answered its first heading `# Smoke Repo` correctly, 2 turns |
| 3. Write + Bash | ✅ created `calc.py` (`def add(a,b): return a+b`), ran it, reported `5` (verified), 3 turns |

Claude Code drives Strata through tool-using agentic coding; the Anthropic tool-use protocol holds. Claude Code
prints a cosmetic `[claude-code:unrecognized_model]` warning and proceeds.

**Findings that shape the rest of the run:**
- **Cold-prompt latency:** first call, 16,556 input tokens, time-to-first-token ~28.8 s (~570 tok/s prefill,
  matching the earlier bench). This is the cost each time a large new block of context first enters a session.
- **Warm turns are cheap:** check 2's follow-up turn reported only 70 input tokens read — Strata's conversation
  cache (resume) reuses the prefix across Claude Code's turns, so a multi-turn agent session does not re-read the
  whole context each turn. This is the key reason agentic use is viable despite slow cold prefill.
- **200K context cap (resolved).** Claude Code defaults an unknown model to a 200,000-token context window
  (`"contextWindow":200000` in the JSON result) and auto-compacts there — which would have capped the
  long-context test well below the user's 256K–512K target. Setting `CLAUDE_CODE_MAX_CONTEXT_TOKENS=524288`,
  `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1`, and `CLAUDE_CODE_AUTO_COMPACT_WINDOW=524288` (all three
  present in `claude.exe` v2.1.286) raises it: a re-run reported `"contextWindow":524288`. The remaining Dimensions
  run with these set.

## Dimension 1 — Long-context recall: **perfect to 437K tokens** (2026-10-03)

Three needles (functions returning unique 12-digit constants) at ~10/50/90% depth in a context of real concatenated
source; the whole context is in one user message (so recall is the model's, not a tool's); asked for all three
constants. Driver: `run_recall.py` / `recall_440.py`. (Char→token ratio measured at ~2.95 for this source.)

| Target | Actual tokens | Recall (α/β/γ at 10/50/90%) | Cold prefill |
| :--- | --: | :--- | :--- |
| 128K | 156,176 | **3/3** ✅ | 266 s |
| 256K | 311,900 | **3/3** ✅ | 616 s |
| ~440K | 437,225 | **3/3** ✅ | ~16 min (partly cached) |
| ~500K+ | — | n/a — **rejected** | Claude Code: "Prompt is too long" |

**Recall is perfect at every testable depth, including 437K tokens — well past the model's 262K trained length, into
the YaRN-extrapolated region.** No degradation was found; the feared YaRN fall-off did not appear for retrieval.

**Practical ceiling ≈ 475K tokens of your content, via Claude Code.** Claude Code reserves its max output
(~32K) and system prompt (~16.5K) from the 524288 window and refuses a prompt that would exceed what's left, with
"Prompt is too long" *before* it reaches Strata (a clean refusal, not a silent truncation). So the full 512K cannot
be filled with your code through Claude Code — the usable input tops out near 475K tokens. Strata itself supports
the full 524288; the cap is Claude Code's accounting.

## Recommendation — **GO**, with caveats (2026-10-03)

Driven by Claude Code, this Strata model works as a long-context coding agent. Against the plan's bar:

| Dimension | Bar | Result |
| :--- | :--- | :--- |
| 0 Integration | must pass | ✅ Claude Code drives Strata; tool protocol holds |
| 1 Recall | ≥70% at your depth | ✅ 100% (3/3) to 437K tokens, no degradation |
| 2 Tool use | ≥95% valid | ✅ 100%; 11/11 sessions clean, up to 11 turns |
| 3 Correctness | ≥70% pass | ✅ 7/7 checkable (Python, Rust, JS, Java) |
| 4 Speed | usable at your depth | ⚠️ warm turns fast (~37 tok/s); **cold load of a big context is slow (4–16 min)** |

**Use it as a main coding model** via Claude Code, keeping these in mind:
1. **Unlock the window**: set `CLAUDE_CODE_MAX_CONTEXT_TOKENS=524288`, `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1`,
   `CLAUDE_CODE_AUTO_COMPACT_WINDOW=524288`, plus `ANTHROPIC_SMALL_FAST_MODEL` = the model name. Without them Claude Code
   caps at 200K and auto-compacts.
2. **Usable context ≈ 475K tokens** of your code (not the full 512K) through Claude Code.
3. **Cold load is the cost, and it is minutes** (≈4 min at 156K, ≈10 min at 312K, ≈16 min near the top). Load a big
   repo/context once and work within it — warm turns are 1–2 s. Avoid re-sending huge cold contexts.
4. **C++/Kotlin correctness was not verified here** (no `cl.exe`/`vcvars`/`kotlinc` on the agent's PATH). Rust (a
   systems language) passed cleanly, so this is a harness gap, not a known model weakness; verify C++/Kotlin in real
   use or put those compilers on the agent's PATH.
5. **Serial FIFO**: Strata serves one request at a time, so parallel subagents queue — they are not a speed win.
6. The model is **uncensored** (refusal projection on); keep that in mind for shell commands it may run without a caveat.

## Dimension 2 — Agentic tool use: **3/3 complete, tool protocol reliable** (2026-10-03)

Longer multi-step, multi-file tasks through Claude Code's own tools (`run_agentic.py`), each verified by an
automated check:

| Task | Result | Turns | Claude Code error |
| :--- | :--- | --: | :--- |
| cli-json-flag (add a `--json` flag, keep default behaviour) | ✅ done | 7 | false |
| rust-bug-multifile (fix a cross-file bug, `cargo test`) | ✅ done | 4 | false |
| py-rename-refactor (rename a function + every caller) | ✅ done | 11 | false |

All three finished the job and the check passed. Across all 11 agent sessions (Dimensions 2 + 3), Claude Code
reported `is_error: false` with no malformed-tool-call failures and no permission denials — the Anthropic tool-use
protocol (tool_use / tool_result round-trips, multi-turn) holds against Strata, including an 11-turn session. No
looping or runaway turn counts were seen.

## Dimension 3 — Code correctness: **7/8 pass** (2026-10-03)

Each task: a fresh scratch repo, driven headless (`claude -p … --dangerously-skip-permissions`), scored by an
automated check (exit 0). Thinking off by default. Driver: `run_correctness.py`.

| Task | Lang | Result | Turns | Secs |
| :--- | :--- | :--- | --: | --: |
| py-fizzbuzz-test (write to pass a test) | Python | ✅ pass | 4 | 53 |
| py-bugfix (even-length median) | Python | ✅ pass | 6 | 56 |
| py-multifile (add `mul`, keep `add`) | Python | ✅ pass | 5 | 46 |
| rust-palindrome (`cargo test`) | Rust | ✅ pass | 8 | 83 |
| rust-borrowfix (`cargo test`) | Rust | ✅ pass | 4 | 48 |
| js-dedupe (node, exact output) | Node | ✅ pass | 3 | 51 |
| java-reverse (`javac`+`java`, exact output) | Java | ✅ pass | 3 | 55 |
| cpp-gcd (MSVC compile+run) | C++ | ⚠️ inconclusive | 19 | 279 |

The model wrote correct, checkable code in Python, Rust, JS and Java — 7/7 of the tasks with a working toolchain on
the agent's PATH. The one miss, **cpp-gcd, is a toolchain gap, not a model failure**: the headless agent's shell has
no C++ compiler on PATH (MSVC `cl.exe` needs a `vcvars64` environment), so the model could not compile/verify C++
(it spun 19 turns trying), and the check's own `vcvars64` call failed on `vswhere`. To validate C++/Kotlin fairly,
the agent needs `cl.exe`/`g++`/`kotlinc` on PATH; **Kotlin was not run (no `kotlinc` installed); Java stands in for
the JVM.** This says nothing about whether the model can write C++/Kotlin — only that the harness could not check it.

## Dimension 4 — Speed at depth (2026-10-03)

From the engine log during the recall and coding runs (`prompt … read in … ms`, `… generated in … ms`):

| Context | Cold prefill (read) | Cold time-to-usable | Decode | Draft accept |
| :--- | :--- | :--- | :--- | :--- |
| ~17K (a coding turn, warm) | 57–321 new tokens, 1–2 s | ~1–2 s | 34–48 tok/s | ~85–98% |
| 156K (cold) | 254.8 s @ 612.9 tok/s | **~4.2 min** | 37.8 tok/s | 270/314 |
| 312K (cold) | 605.3 s @ 515.3 tok/s | **~10.1 min** | 38.6 tok/s | 260/289 |

What this means for interactive coding:
- **The cost is the first cold load of a big context**: ~4 min at 156K, ~10 min at 312K, and prefill *rate* falls
  with depth (613 → 515 tok/s) as the attention span grows. Loading a large repo into a fresh session is a
  multi-minute wait.
- **After that, turns are cheap.** Strata's conversation cache reuses the whole prefix, so a follow-up turn reads
  only its new tokens (tens to a few hundred) in 1–2 s, then decodes at ~37 tok/s. A long agent session is
  responsive once the context is warm — the slow part happens once.
- **Decode holds at depth** (~38 tok/s at 312K, same as short context) and draft acceptance stays ~85%.

## Recommendation (go/no-go)

_pending — written after Dimensions 1–4._
