# Gyro-S v2 vs UD-Q2_0 — RTX 3060 12 GB, 2026-11-26

**Verdict: UD-Q2_0 stays prod. Gyro-S v2 was measured in full and deleted the same day.** v2 is a real quality
update over v1 (KLD 0.331 against 0.401, tool-call drift -27%), and on this PC it wins on memory (24.0 against
~35 GiB), expert slots (3,723 against 2,336) and prefill (+4..10%). It loses where the daily work happens:
**decode is 31-44% slower** and the tasks we ran score lower (HumanEval-60 55/60 against 58/60; 9/12 against
12/12 on the reasoning set). 58.5 GB is not worth keeping for a memory win this PC does not need.

## What was compared

| | UD-Q2_0 (prod) | Gyro-S v2 |
|---|---|---|
| Pack | `models\UD-Q2_0`, 65.7 GB | `agentionai/Qwen3.8-Flash-Next-Gyro-GGUF` @ main (repo `cd23c647`), 58,487,015,808 B, SHA-256 `1a8267c2…` |
| Tensor types | UD-Q2_0 (2-bit dynamic) | TQ1_0 (Gyro trellis, Hadamard-rotated experts) |
| Pack dir | `packs\ud_q2_0` | `packs\gyro-s` (built by `terminal\tools\iq_pack.py --compat-bf16`: 1,079 tensors, 302 native, arena 1.43 GiB, 364 tensors rounded to BF16, max err 0.0144) |
| Engine / flags | `build-v034\strata.exe` 0.1.69 | same |
| Context / KV | 262,144, `--kv q4_0`, `--kv-resident 32768` | same |
| Drafter | MTP `basalt-rt` + `draft_vocab-vi-en-code.bin`, `--spec 4 --spec-min-p 0.7` | same |
| Env | `STRATA_EXPDEC=1 STRATA_PLE_AUTO_MMAP=1 STRATA_PCIE_BALANCE=1 STRATA_PF_SMALL=0` | same |
| Control vector / vision | on | on |
| Serve | 18080 (router 8081), `terminal\strata-ud-q2_0-tuned.json` | 18082, `terminal\strata-gyro-s-v2.json` (deleted) |

Both serves used the prod config's server-level keys (API key, `system_prompt`, origins, MCP, reasoning, cache);
only the model keys changed. The Gyro serve was given a copy of the learned expert profile so both sides start
pre-filled.

Load: Gyro-S **24.02 GiB** at 4.75 GiB/s, 3,723 slots, 1,554 MiB VRAM free, **12.1 GB RAM free**.
UD-Q2_0: ~35 GiB, 2,336 slots, 1,540 MiB VRAM free, 2.6-3.8 GB RAM free.

## Speed (cold prompts, same engine/flags)

| Row | UD-Q2_0 | Gyro-S v2 | Gyro vs UD |
|---|---:|---:|---:|
| 13K prefill / decode | 779-800 / **34.9-35.3** | **855** / 24.1 | +7% / **-31%** |
| 13K cache re-read | 35 tok, 0.65 s, 40.6 decode | 35 tok, 1.04 s, 29.6 | slower first token |
| follow-up (289 tok) | 39.3 | 27.8 | -29% |
| 55K prefill / decode | 1,000-1,004 / **42.7-43.9** | **1,046** / 26.4 | +4% / **-38%** |
| 167K prefill / decode (200 gen) | 941 / **51.4** | **982** / 28.6 | +4% / **-44%** |
| 128K needle prefill / decode | 977 / **42.3** | **1,232** / 27.5 | +26% / -35% |

Prefill is consistently better; **decode is 31-44% worse at every length**, and it does not improve with the
bigger expert cache (3,723 slots, hit 0.57-0.72). The TQ1_0 expert kernels are the cost on sm_86; draft
acceptance was actually higher (70/75 at 13K). The old v1 test (engine 0.1.52) showed the same direction:
decode 13-26% slower than q2_0, prefill better on short prompts.

## Quality

| Test | UD-Q2_0 | Gyro-S v2 |
|---|---|---|
| HumanEval-60, pass@1 (hidden tests) | **58/60 = 96.7%** | 55/60 = 91.7% |
| Codebench 10 tasks | **10/10** | **10/10** |
| 12 fixed reasoning questions | **12/12** | 9/12 |
| `get_weather` tool call | PASS | PASS |
| 128K needle at 90% depth | PASS (`ORANGE-7421`) | PASS (`ORANGE-7421`) |
| 29 KB page fix (syntax + arrow) | PASS, 24,344 tok, 458 s | PASS, 24,404 tok, 894 s |
| Vision (42, red circle) | PASS | PASS |

Details:

- **HumanEval-60 failures.** UD-Q2_0: `decode_shift` (NameError) and `closest_integer` (SyntaxError).
  Gyro-S v2: the same two plus `sort_array` (AssertionError), `specialFilter` (SyntaxError) and
  `generate_integers` (AssertionError). Gyro's tasks also took 12-149 s against 5-88 s.
- **Reasoning misses (Gyro):** Wednesday + 100 days -> "Saturday" (right: Friday), bat and ball -> 0.1
  (right: 0.05), clock at 3:15 -> 37.5 degrees (right: 7.5). All at temperature 0, `reasoning_effort: none`.
- **The one thing Gyro did better:** the page fix was the cleanest of the three models measured - it added the
  missing arrow and changed nothing else. UD-Q2_0 also rewrote `blob` to an arrow (functionally identical);
  ISTA IQ2_XS broke a correct `ctx.arc` (zero-length). Both Gyro and UD left the input's mojibake title alone.

## What v2 changed over v1 (from the model card)

Same file name, size and tensor types; the weights are closer to the original model: mean KLD held-out
**0.331** against 0.401 (-18%), tool-call transcripts 0.451 against 0.617 (-27%), code 0.094 against 0.109
(-14%), web 0.190 against 0.214 (-11%), out-of-domain 0.205 against 0.239. Against ISTA IQ2_XS (68 GB) it is
21% closer on held-out text, 30% on tool calls and 20% on code. Agentic coding is on par with v1 (Marshall
134/152 against 135/152; IQ2_XS 133/152), and it loops less (1 in 80 runs against 2). **No speed change** -
the card says the speed rows are v1 and v2 has the same size/tensor types; our measurements agree.

Two practical notes for a retry:

- **Strata's setup still downloads v1.** `terminal/setup.py` pins `agentionai/Qwen3.8-Flash-Next-Gyro-GGUF` at
  revision `1ada0842` (2026-10-13). Use `.orca/gyro-s-dl.py` (it resolves `/main`, i.e. v2) or update the pin.
- v2 has not been tested in Strata by its author; the format is identical, and it loaded and served here on
  0.1.69 without changes (pack v5, 302 native tensors).

## Why it was deleted

On this 47.7 GB PC the memory saving (12 GB of RAM free against 2.6-3.8) buys nothing: UD-Q2_0 fits and is
faster and more accurate on both test sets. Gyro-S remains the right pick for a PC where the model must fit
in less memory (the card targets 32 GB cards, 16-24 GB with Strata's expert cache) - not here. The 58.5 GB
model, the `packs\gyro-s` dir, the staged config, the copied expert profiles, the engine log and the 18082
server were removed on 2026-11-26; D: back to 228.6 GB. Prod UD-Q2_0 was warmed again (2,336 slots, MTP,
1,540 MiB VRAM free).

## How to retry quickly

1. Download (v2, `/main`; verify `1a8267c29026748ac7445e37b2f9d50c27aa30426be8eab70a30c7fa019264f0`):

   ```powershell
   .venv\Scripts\python.exe .orca\gyro-s-dl.py      # 58,487,015,808 B -> models\Qwen3.8-Flash-Next-Gyro-GGUF
   ```

2. Pack:

   ```powershell
   .venv\Scripts\python.exe terminal\tools\iq_pack.py --gguf <...>\Qwen3.8-Flash-Next-Gyro-S-TQ1_0.gguf `
     --out D:\GitHub\Strata-data\packs\gyro-s --compat-bf16
   ```

3. Copy `terminal\strata-ud-q2_0-tuned.json` to `terminal\strata-gyro-s-v2.json` and change: `--pack` ->
   `packs\gyro-s`; `--native` -> the Gyro GGUF; **remove `--ple-gguf`** (the full file carries the table);
   `--expert-profile` -> a copy; `model_name` -> `qwen3.8-flash-next-gyro-s`; `port` -> 18082; `tokenizer` ->
   `packs\gyro-s\tokenizer`; `vision.model` -> the Gyro GGUF; `expert_profile_save` -> a new name (copy the
   learned `expert-profile-learned-ud-q2_0.bin` to it so the slots start pre-filled).
4. Serve on 18082 (`.orca\serve-variant.ps1`), then re-run: `bench-pack-ab.py`, `long-decode.py`,
   `codebench.py`, `codebench_humaneval.py … 60`, `qa12.py`, `toolcall.py`, `needle-depth.py … 1100 90`,
   `filefix.py`. Expected rows are the tables above.

## Files

- Results: `.orca\gyro-v2-bench.txt`, `gyro-v2-167k.txt`, `gyro-v2-codebench.txt`, `gyro-v2-qa12.txt`,
  `gyro-v2-tool.txt`, `gyro-v2-needle.txt`, `gyro-v2-filefix.txt`, `humaneval-gyro-v2-60.log/.json`,
  `humaneval-udq20-60.log/.json`, `codebench-gyro-v2.json`, `car-page-gyro-v2.html`.
- Download / pack: `.orca\gyro-v2-dl.log`, `.orca\pack-gyro-s-v2.log`.
- Scripts: `.orca\gyro-s-dl.py`, `serve-variant.ps1`, `bench-pack-ab.py`, `long-decode.py`,
  `codebench.py` (+ `codebench_tasks.py`), `codebench_humaneval.py`, `qa12.py`, `toolcall.py`,
  `needle-depth.py`, `filefix.py`.
- Prod config: `terminal\strata-ud-q2_0-tuned.json`; engine `D:\GitHub\Strata-data\build-v034\strata.exe`.
