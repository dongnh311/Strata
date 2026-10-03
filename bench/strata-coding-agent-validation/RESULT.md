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

## Dimension 2 — Agentic tool use

_pending_

## Dimension 3 — Code correctness (Rust / C++ / Kotlin / …)

_pending_

## Dimension 4 — Speed at depth

_pending_

## Recommendation (go/no-go)

_pending — written after Dimensions 1–4._
