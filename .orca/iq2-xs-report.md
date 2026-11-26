# ISTA-DASLab IQ2_XS vs Unsloth UD-Q2_0 — RTX 3060 12 GB, 2026-11-26

**Verdict: UD-Q2_0 stays prod. IQ2_XS was deleted after the test.** It is faster at long generation and holds
more experts in VRAM, but it prefills 5-19% slower, gets one logic item wrong reproducibly, and made an
unforced regression in a 29 KB page edit. 63.4 GB of model + 68 GB of download are not worth keeping for that.

## What was compared

| | UD-Q2_0 (prod) | ISTA IQ2_XS |
|---|---|---|
| Pack | `models\UD-Q2_0`, 65.7 GB, 3 shards | `models\IQ2_XS`, 63.4 GB, 2 shards (`ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF`) |
| Engine | `build-v034\strata.exe` 0.1.69 | same |
| Context / KV | 262144, `--kv q4_0`, `--kv-resident 32768` | same |
| Drafter | MTP `basalt-rt` + `draft_vocab-vi-en-code.bin`, `--spec 4 --spec-min-p 0.7` | same |
| Env | `STRATA_EXPDEC=1 STRATA_PLE_AUTO_MMAP=1 STRATA_PCIE_BALANCE=1 STRATA_PF_SMALL=0` | same |
| Server | 18080 (router 8081), `terminal\strata-ud-q2_0-tuned.json` | 8080, `terminal\strata-iq2_xs-tuned.json` (deleted) |

The launcher first prepared the pack and served it on engine 0.1.57 (`strata launch --family qwen --model IQ2_XS
--data-dir D:\GitHub\Strata-data --context 256k --vision gpu --drafting mtp --yes --no-tui --port 8080`);
every number below is the same pack re-served by 0.1.69 with the prod flags, so the engine and the settings
do not explain the differences.

## Speed (cold ladder, random salt in each prompt, `.orca/ladder.py`)

| Context | Prefill UD / IQ2 (tok/s) | Decode UD / IQ2 (tok/s) |
|---:|---|---|
| 4K | **719** / 607 | 28.6 / 26.7 |
| 8K | **1020** / 854 | 31.5 / 36.0 |
| 16K | **1019** / 917 | 32.9 / 42.4 |
| 32K | **992** / 928 | 38.5 / 45.7 |
| 64K | **1001** / 963 | 45.9 / 39.1 |
| 128K | **975** / 926 | 42.3 / 47.2 |

Prefill: UD-Q2_0 is 5-19% faster at every length. Decode: IQ2_XS is ahead at 8-32K and 128K, behind at 4K/64K;
the draft acceptance moves that row more than the quant does. The solid long-generation signal is the page fix
below: the same 24,344 output tokens took **335 s on IQ2_XS against 458 s on UD-Q2_0** (-27%).

Other rows: `.orca/bench-pack-ab.py` (13K/55K/199K) gave IQ2_XS 812/953/880 prefill and 43.5/47.3/49.2 decode
against UD-Q2_0 854/1,013/906 and 42.1/43.0/40.0. Expert slots: **3,041 IQ2_XS against 2,336 UD-Q2_0** (the
i-quant experts are smaller). Cache re-read: 35 tokens, first token 0.58 s (UD 0.59). Vision both ("42, a circle").

## Quality

| Test | UD-Q2_0 | IQ2_XS |
|---|---|---|
| 10-task code suite, hidden pytest per task (`.orca/codebench.py`) | **10/10** | **10/10** |
| 12 fixed questions (`.orca/qa12.py`) | **12/12** | 11/12 |
| `get_weather` tool call (`.orca/toolcall.py`) | PASS | PASS |
| 128K needle at **90% depth** (`.orca/needle-depth.py`) | PASS (`ORANGE-7421`), 977 tok/s / 42.3 | PASS, 942 / 50.6 |
| 199K needle at 50% depth | (earlier 180K needle passed) | PASS (`ORANGE-7421`) |
| 29 KB page fix (`.orca/filefix.py`, `--reasoning_effort high`, 32K output) | PASS, 24,344 tok, 458 s | syntax PASS, 24,344 tok, 335 s — **but see below** |
| Vision | PASS | PASS |

The reproducible quality misses of IQ2_XS:

1. **Wednesday + 100 days -> "Saturday"** (right: Friday), in both the six-question and the twelve-question runs
   at `temperature 0`.
2. **An unforced regression in the page fix.** The bug was a missing `=>` in `forEach(s, L.pole, (x, j, i) {`.
   IQ2_XS fixed that, but also rewrote a correct line, `ctx.arc(x, y, r, 0, Math.PI * 2)` (a full circle), as
   `ctx.arc(x, y, r, 0, 0, Math.PI * 2)` — a zero-length arc, so the page's particles would not draw. `node
   --check` and the arrow check pass; only reading the diff catches it. UD-Q2_0 also rewrote that function
   (as `const blob = (...) => {...}`) but kept the 5-argument arc, so its page still draws. Both left the
   mojibake title of the buggy file as it was.

## Why it was deleted

The trade was: **+25-30% long-generation speed and +30% expert slots, against -5-19% prefill, one wrong logic
item, and less careful edits.** For an agent that reads a codebase more than it writes a whole file, prefill and
careful edits win, so UD-Q2_0 stays prod and the 63.4 GB pack was removed on the owner's call (2026-11-26).
The comparison is only worth repeating if the work changes to long single-shot generation, or if a later engine
build changes the i-quant kernels.

## How to retry quickly

1. Download + prepare (68 GB, ~25 min on this line; it continues after an interrupt):

   ```powershell
   strata launch --family qwen --model IQ2_XS --data-dir D:\GitHub\Strata-data --context 256k `
     --vision gpu --drafting mtp --yes --no-tui --port 8080
   ```

2. Rebuild the tuned config from the prod one (`terminal\strata-ud-q2_0-tuned.json`), changing only:
   `--pack` -> `D:\GitHub\Strata-data\packs\iq2_xs`; `--native` ->
   `...\models\IQ2_XS\Qwen3.8-Flash-Next-GSQ-RCO-IQ2_XS-00001-of-00002.gguf`; `--ple-gguf` ->
   `...-00002-of-00002.gguf`; `--expert-profile` -> a copy in `terminal\data\expert-profile-iq2_xs.bin`;
   `model_name` -> `qwen3.8-flash-next-iq2_xs`; `port` -> 8080; tokenizer ->
   `D:\GitHub\Strata-data\packs\iq2_xs\tokenizer`; `vision.model` -> the IQ2_XS shard 1. Everything else
   (KV, MTP, env, cache, key, system prompt) stays.
3. Start: `.venv\Scripts\python.exe terminal\serve\server.py --engine strata --config terminal\strata-iq2_xs-tuned.json --port 8080`.
4. Re-run the battery:

   ```powershell
   .venv\Scripts\python.exe .orca\codebench.py iq2xs http://127.0.0.1:8080 qwen3.8-flash-next-iq2_xs .orca\codebench-iq2xs.json <api_key>
   .venv\Scripts\python.exe .orca\qa12.py 8080 qwen3.8-flash-next-iq2_xs iq2xs
   .venv\Scripts\python.exe .orca\toolcall.py 8080 qwen3.8-flash-next-iq2_xs iq2xs
   .venv\Scripts\python.exe .orca\needle-depth.py 8080 qwen3.8-flash-next-iq2_xs 1100 90 iq2xs
   .venv\Scripts\python.exe .orca\ladder.py 8080 qwen3.8-flash-next-iq2_xs iq2xs
   .venv\Scripts\python.exe .orca\filefix.py 8080 qwen3.8-flash-next-iq2_xs iq2xs .orca\car-page-iq2xs.html
   ```

Expected rows are the tables above; any large departure means the engine, the flags or the card changed.

## Files

- Results: `.orca\deep-*.txt`, `.orca\codebench-iq2xs.json`, `.orca\bench-iq2_xs-244k*.txt`,
  `.orca\qa-iq2xs.txt`, `.orca\car-page-iq2xs.html` (kept as the record of the bad arc edit).
- Scripts: `.orca\codebench.py` (+ `codebench_tasks.py`), `qa12.py`, `toolcall.py`, `needle-depth.py`,
  `ladder.py`, `filefix.py`, `bench-pack-ab.py`, `bench-244k-one.py`, `qa-qwen.py`.
- Prod config: `terminal\strata-ud-q2_0-tuned.json`; engine `D:\GitHub\Strata-data\build-v034\strata.exe`.
