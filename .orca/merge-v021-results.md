# Verify merge v0.2.1 — 2026-10-21 (all gates green)

## Mergetree (final commits)
- `891ef816` serve: preserve the fork's pre-merge work (7 files; MCP picture results, slash menu, ctx meter)
- `7646f233` Merge tag 'v0.2.1' into windows-coding (5 conflicts resolved: keep both intents)
- Branch: `windows-coding`, ahead of origin by 3 (c5241690, 891ef816, 7646f233)

## Gates (same procedure as the pre-merge run)
- Build: `.orca\build-q36.cmd` -> iq_parity.exe / native_expert_parity.exe / strata-q36.exe fresh, CUDA ok
  (log: `.orca\build-merge-log.txt`). New in 0.2.1 compiles in: ggml-tq-overlay mmq instances (tq2_t/tqk6/tqk7),
  STRATA_Q8_SM60, 5..8-col mmvq_il, trellis CPU kernels (tq_cpu/tq_avx2/tq_avx512).
- `iq_parity` on the regenerated fixture (11 fixtures, seed 7): **0 failures** — dequant rel 0.00e+00 bitwise for
  all 11 types incl. IQ1_S (19) and Q3_K (11); mmvq ncols 1..8 within bound.
- `native_expert_parity`:
  - `--synthetic q4_K/q5_1`: ok (cpu rel 1.37e-02, gpu 1.25e-02; decode-once vs per-entry bitwise)
  - `--q2k-trim iq2_xxs q4_K` + `... q4_K`: ok (212 B rows, dequant 0/1638400 differ)
  - `--q4_1-pair iq2_xxs q4_K`: ok (q5_1 twin: 0 of 7680 values differ, cpu and gpu)
- strata-q36 + Ornith-122B (cold, n=64, mtp 0, kv q8_0, ctx 4096, 12 old prompt ids):
  899 tensors layout-checked, 5.08 GiB/3.3 s, 21/256 slots, 37.38 GiB host; **VERIFY: 18432 comparisons,
  0 mismatches** (identical to pre-merge). decode 3.9 t/s cold (pre-merge cold run: 4.0).
- Perf A/B (warm, n=128, same prompt):
  - MTP0, 21 slots: **5.4 t/s** (23.59 s), cover 24.1% (12878/53376), pool 40498/18.59 s, 861 swaps
    — pre-merge baseline identical (5.4 / 24.1% / 40498 / 861); first 128 gen ids identical to pre-merge greedy.
  - MTP2 + --expert-vram 3.8: **6.3 t/s** (20.33 s) on run 2, accept 72/114 (63%), cover 28.9% (19870/68736),
    pool 48866/17.84 s, 927 swaps — pre-merge baseline identical (6.3 / 72/114 / 28.9% / 48866 / 927).
    (First MTP2 sample 5.9 t/s / pool 18.66 s — environment noise; counts all identical.)

## Conclusion
- v0.2.1 merged with fork's fixture-verified fixes intact; all measured numbers reproduce the pre-merge baseline.
- serve/ web UI files untouched by upstream (no conflict); user's save-side features rechecked on restart.
- qwen serve restored via run-q2_0-v144-refusal.bat after the 122B gates (see below for the restart check).
