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

## Dimension 1 — Long-context recall (256K–512K)

_pending_

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

## Dimension 4 — Speed at depth

_pending_

## Recommendation (go/no-go)

_pending — written after Dimensions 1–4._
