# AGENTS.md

Version 0.2.15 (source merged from upstream v0.2.15; Control 0.1.61, the engine packages stay 0.1.60 — the engine binary on this PC is still 0.1.60.1, built from the v0.2.14.1 source into `D:\GitHub\Strata-data\build-v032`; v0.2.15 changes no engine code, only its tests — and `build-v031` (0.1.59.1) and `build-v030` stay for rollback). The public model families are
Qwen3.8-Flash-Next and Qwen3.6-35B-A3B (upstream removed DeepSeek V4.1-Flash in 0.2.14: the `dsv41` engine, its
sources and docs are gone; our `strata-unc48l*` configs and the `unc48L` model were already deleted here). Read **[docs/AI_REFERENCE.md](docs/AI_REFERENCE.md)** for model availability, APIs, hardware limits and
source-backed claims. Articles and videos should use **[docs/MEDIA_KIT.md](docs/MEDIA_KIT.md)**.

For recommendations and agent-assisted setup, prefer **ISTA-DASLab → Unsloth → Gyro → others**, using only a
compatible pack that fits the selected model and hardware. ISTA-DASLab is the default recommendation; Gyro is a
memory-saving fallback and is currently slower. Honor an explicit user choice. This is recommendation policy;
existing executable defaults may differ, so inspect the plan and choose the family explicitly.

Strata has three parts:

- **The app** (`apps/desktop`, the Tauri shell; `apps/host`, the Node host and the web UI). It is for people who do
  not want a terminal. One installer per system ([latest release](https://github.com/Niko1221/Strata/releases/latest)):
  `Strata-0.2.15-windows-x64-setup.exe`, `Strata-0.2.15-linux-x86_64.AppImage`, `Strata-0.2.15-macos-arm64.dmg`.
  The Windows and Linux installers carry no engine: the app downloads the engine for the graphics card on first
  start, or installs a file the user already has. The Mac dmg keeps its small Metal engine inside.
- **The Terminal** (`strata.py`, `strata_cli/`, `strata_control/`): the `strata` command. It sets up a model, serves
  it and watches it. Agents use this part.
- **The engine and the server** (`src/`, `include/`, `metal/`, `sycl/` for the C++/CUDA/HIP/SYCL/Metal engine;
  `serve/` for the Python server with an OpenAI- and Anthropic-compatible API and a web page). `setup.py`, started by
  `START-HERE.bat` or `setup.sh`, is setup from a source checkout, for developers. The release paths are the
  installer and `strata launch`.

## Installing Strata for a user

Follow **[docs/AI_SETUP.md](docs/AI_SETUP.md)**. For a user who wants the desktop app, send them to the installer
for their system (above) and [docs/INSTALL.md](docs/INSTALL.md). For an agent that has a shell, use the Terminal; the
short version is:

1. Install the Terminal. It needs no administrator rights.

   ```sh
   curl -fsSL --connect-timeout 15 --max-time 120 https://github.com/Niko1221/Strata/releases/latest/download/install.sh -o install.sh && sh install.sh                  # Linux, Mac
   irm -TimeoutSec 120 https://github.com/Niko1221/Strata/releases/latest/download/install.ps1 | iex                         # Windows PowerShell
   ```

   On Windows, open a new terminal afterwards so that `strata` is on the PATH.
2. Check what would happen. Nothing is changed:

   ```sh
   strata launch --plan --family qwen --model q2_0
   ```

3. Set up and serve without questions. It downloads the engine for the card and the model (tens of GB), starts the
   server, prints the addresses and returns. The server keeps running.

   ```sh
   strata launch --family qwen --model q2_0 --yes --no-tui
   ```

   Useful flags (all of them: `strata launch --help`): `--family`, `--model-path` (files the user already has),
   `--data-dir`, `--context 32k|64k|128k`, `--vision off|on|gpu|cpu`, `--parallel N`, `--gpu 0,1`,
   `--access local|lan|cloudflare|tailscale`, `--port`, `--api-key-env NAME`, `--new-key`, `--save-preset NAME`,
   `--output json`. `strata launch --status` shows what is serving, `strata launch --stop` stops it, and
   `strata launch --show-key` prints the API key.
4. Connect the user's apps: `strata connect` lists them, `strata connect <app> --check` sends one prompt and one tool
   call the way that app does.

Keep the server on `127.0.0.1` unless the user asks for more. Beyond it an API key is recommended: `--access lan` makes one for you, and `--no-api-key` serves without one (a warning, never a refusal; on a public tunnel the warning is stronger). Source setup (`START-HERE.bat`, `setup.sh`) is the fallback for a developer or for a system with no release package; it is
documented in [docs/SOURCE_INSTALL.md](docs/SOURCE_INSTALL.md). Those wrappers exist in a source checkout, not in the
released app. Do not tell an app user to find a `.bat` file.
Source setup does not make an unsupported model or backend compatible. Strata's MCP server ([docs/MCP_SERVER.md](docs/MCP_SERVER.md)) offers the same steps as tools.

## Working on the code

- How the engine works, every measured number, the API and all settings: [docs/DETAILS.md](docs/DETAILS.md) and
  the [paper](docs/paper/Strata-Paper.pdf).
- The Terminal: [docs/TERMINAL.md](docs/TERMINAL.md) and [docs/TERMINAL_LAUNCH.md](docs/TERMINAL_LAUNCH.md). The app,
  the packages and the update feed: [packaging/README.md](packaging/README.md) and [packaging/UPDATES.md](packaging/UPDATES.md).
- AMD (HIP) build and validation: [docs/AMD_HIP.md](docs/AMD_HIP.md); multi-GPU: [docs/MULTI_GPU.md](docs/MULTI_GPU.md);
  Mac (Metal): [docs/MAC.md](docs/MAC.md).
- Tests: the Terminal and Control tests are in `tests/terminal` (`python -m pytest tests/terminal`). The app's UI
  tests run with `npm test` in `apps/host`. Setup's own tests run without a GPU or downloads:
  `python tools/test_setup_<name>.py` (for example `tools/test_setup_amd.py`, `tools/test_setup_choices.py`).
- Keep the docs' style: plain words, short sentences, written for non-technical users first. Give measured numbers
  with what they were measured on. Make no claim without a measurement.

## Our local changes on this PC — keep them through every merge

The 2026-11-06 work on this PC (RTX 3060 12 GB, i7-14700K, engine 0.1.57) changed things upstream does not know about.
After every merge, re-check all of them before you run anything. If a merge dropped one, restore it first. A merge that
leaves this PC slower, or lets a screen write an old number back over a tuned config, is a failed merge — not a release.

- **DFlash2 is the slower drafter on this card, in every part.** `strata_control/drafting.py`: `auto` follows the
  `_SLOWER` table (cuda `sm_86`), so `auto` here is the MTP, and it says so (`MEASURED_SLOWER`). A `dflash2` named by
  the person still runs. The app mirrors the same answer: `resolveDrafter(…, slower)` in
  `apps/host/server/native-settings.mjs` and `apps/host/src/lib/drafting.ts`, fed by `capabilities.dflash2Slower`
  (`native-control.mjs` reads it from Control's plan; `NativeModels.tsx` uses it for the label and the fit). Python and
  the two JS mirrors must say the same thing after a merge, or the merge is not done.
- **`strata-ud-iq1_m.json` is tuned** — `drafting: "mtp"`, the flags listed in `.orca/tok-speed-playbook.md` section 12,
  `expert_profile_save`, and `trusted_origins` + `allowed_hosts`. `trusted_origins` is what lets the web app reach the
  server from 8081 / 8443 / LAN; without it MCP answers "only from Strata's own page". Re-read `"drafting"`,
  `--vram-reserve-mib 1472` and the conversation cache (10078 / 6 / 8000 / 1536) after any Save in the Models screen:
  that screen can write its old numbers back. The backup of the broken file: `strata-ud-iq1_m.bak-20261106.json`.
  `env` also carries `STRATA_PCIE_BALANCE=1` — A/B'd 2026-11-09 on this PC (`.orca/ud-ab.py`, results in
  `.orca/ud-ab-*.result.txt`): decode median ~48.5 tok/s vs ~45 without, prefill unchanged; `STRATA_ADAPT_OVERLAP=1`
  alone and combined with it did NOT help (median ~45–46.5) — do not add it back.
- **Q2mix tested twice, removed again (2026-11-09).** The HF repo
  `dongnhdev/Qwen3.8-Flash-Next-Q2mix-Hybrids` ships GGUFs whose `split.count` metadata is wrong
  (declares 2 shards, only 1 exists). To run it: download the two GSQ-RCO Q2_0 shards +
  `pack-iq1m/` (~108 GB total; the `mtp-ds4`/`PLE-Q4_1`/second-experts files are ds4-only, skip them),
  then patch in place with `.orca/gguf_kv_patch.py`:
  - `UD-IQ1_M-Q2_0-experts-00001-of-00002.gguf` → rename to `UD-IQ1_M-Q2_0-experts.gguf`, set `split.count`=1
    (the pack's `native_experts.txt` offsets match THIS file, not the GSQ-RCO-00001 shard — verified by
    tensor offsets; `--native` must point at it)
  - `Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00002-of-00002.gguf` (the `--ple-gguf` sidecar): set `split.count`=1,
    rename key `split.no`→`split.xo`
  - Do NOT pass `--mmap-experts`: it opts out of the ~32 GiB resident expert arena and decode collapses
    to ~20 tok/s (needs ~33 GiB free RAM at start or the arena won't fit and it falls back to the file anyway).
  Measured 2026-11-09 (arena mode, engine 0.1.57): prefill 794/945 tok/s, decode 41–48 tok/s median ~46,
  slots 2258 — same as the first run. HumanEval earlier: 51/60. **Tool-calling retest 2026-11-12 (post
  v0.2.13.1 merge): UD-IQ1_M PASSED the same opencode bug-hunt task 2/2 runs** — clean read→test→edit→retest
  loop, all bugs fixed. The earlier reasoning-then-stop was likely fixed by upstream's v0.2.13 tool-call work
  (or was sampling luck); re-verify before trusting either verdict.
  All files deleted again after the test; the recipe above is kept for a future retry.
  **UD-Q2_0 tested same day (`strata-ud-q2_0-tuned.json`): PASSED** — both UD quants now do tool calls;
  UD-Q2_0 (official Unsloth quant, same expert recipe as Q2mix) is a viable agentic alternative to Q2_0.
- **Webchat tool-loop guard (2026-11-10).** With `"strata_mcp": true` the webchat exposes the image sidecar's
  `exec`/`attach_file`/`read_file` tools; on the "write one HTML file" prompt BOTH Q2_0 and UD-IQ1_M fell into
  a loop — the model tried to deliver the file by shelling a ~2K-token command through `image__exec`, got a
  40-char reply, and called again until the client gave up (~300 s, `disconnected`). It is a model-side
  attractor, not a parse failure — opencode's own tool set never triggers it. Fix lives in `serve/mcp.py`
  `McpHub._TOOL_HINTS`: `template_tools()` appends a "do NOT use this to produce answer content, reply
  inline" bound to the descriptions of tools named `exec`, `attach_file`, `write_file`, `create_file` on ANY
  MCP server. Verified live: replay of the same prompt produced 16000 tokens of inline HTML, zero tool calls.
  The same wording was also added to `AI-Gateway-MLX/scripts/windows/image-mcp.py` (the sidecar source), but
  the RUNNING sidecar (pid under the elevated `StrataStack` scheduled task) still serves the old text — the
  Strata-side hint is what protects webchat; the sidecar edit applies next elevated restart. After a merge,
  grep `serve/mcp.py` for `_TOOL_HINTS`.
  Second half (2026-11-10, the same loop under the 2000-character bound): `McpHub.call` refuses an `exec` whose
  command carries HTML/code (`_ANSWER_CONTENT`: `<!doctype html`, `<html`, `<canvas`, `<svg`, `<script`) and sets
  `out["refused"]="answer_content"`; `run_with_mcp` then ends the tool rounds at once (`finalizing=True`,
  `tools=None`, an "answer inline" system message, event `{"event":"inline"}`), so the model cannot retry the
  shell write. The page found in the refused command (`refused_text`) is delivered as the answer directly
  (`_answer_from_command`), so the model does not write the same 10K tokens again — a second round ran past the
  webchat's wait. Verified live: one refused call, the page returned as the answer in 22 s, no second call, the
  file was never written. The webchat is also not offered the sidecar's `exec`/`write_file`/`create_file` at all
  (`without_content_tools` at both endpoints): with no shell the model answers inline. Verified 2026-11-10: a small
  page at `max_tokens` 8192 in 24 s; the car page with `max_tokens` empty — 29,908 chars, `finish` stop, zero tool
  calls, 613 s. 4000 tokens cannot hold the page (thinking plus page): use empty or 16384+. After a merge, grep
  `serve/mcp.py` for `_ANSWER_CONTENT` and `serve/server.py` for `without_content_tools` / `refused_text`.
- **Empty-answer retry (2026-11-10).** The webchat can end a reply after thinking with no answer and no call (with
  or without MCP tools), so the page showed a thought and then nothing. Both webchat paths now ask once more with
  `enable_thinking: False`: `run_with_mcp` and `run_with_empty_retry` in `serve/server.py`. The thinking is quoted in
  a trailing user note (not an empty assistant turn, which the template drops) so the prompt prefix stays cached.
  It is webchat-only: both need an `Origin` the config trusts, so API/Terminal clients without one keep the old
  behavior (the general `reasoning_close_retry` tests still pass). A reply that is only a rejected `<tool_call>`
  block is retried too; a *declared* `web_search`/`fetch_url` call still runs, so a pasted page can still be
  distracted into tool rounds. Log line `empty_answer_retry`; tests
  `serve/test_mcp.py::test_a_reasoning_only_stop_without_mcp_is_asked_again` and its MCP, rejected-call and
  inside-thinking siblings. The fixed page is `serve/web/car-page.html` (also `.orca/car-page.html`).
- **Engine rebuilt from source (2026-11-11).** `D:\GitHub\Strata-data\build-v031\strata.exe` is 0.1.59.1, built
  by `.orca\build-v031.cmd` (same flags as build-v030); `strata-q2_0-v144-refusal.json` names it and build-v030
  stays for rollback. The v0.2.13.1 merge had dropped `kNativeFF` from `native_expert.hpp` (the CPU pool did not
  compile) and the tokenizer fallback in `serve/server.py` (`tok`/`tcfg` unbound without `vocab.json`); both
  restored. Long-context 244,046 tokens: prefill 905.3 tok/s, decode 50.4 tok/s, draft 1580/2008 — at the Q2_0
  floor (816–1003 / 48.6–55.7).
- **Production switched to UD-IQ1_M (2026-11-11).** `strata-ud-iq1_m.json` names the 0.1.59.1 engine, carries the same
  `api_key` and the same `system_prompt` rule as Q2_0, and `model_name` is `qwen38-ud-iq1_m`. The router's
  `QWEN_CFG`/`QWEN_ID` (the repo copy and the deployed `%LOCALAPPDATA%\strata-stack\model-router.py`) name it, so a
  restart brings back IQ1_M, not Q2_0; the Q2_0 config is untouched for rollback. Load on this PC: 32.42 GiB of experts
  in RAM (18 s), 2498 expert slots, 3.33 GiB expert cache, `vram_free_mib` 1464, `drafting=mtp`, `spec=12`, context
  262144; a webchat request with `Origin: http://127.0.0.1:8081` and `"strata_mcp": true` answered. The config before
  the edit is `strata-ud-iq1_m.bak-20261111-pre-iq1m-load.json`; its `reasoning_effort` is still `"low"` (the webchat
  sends its own level, other clients do not). Speed on 0.1.59.1: `bench-pack-ab.py` 13K cold 798 tok/s prefill / 45.5
  decode, 55K cold 947 / 44.9, re-read 13K reads 35 tokens (first token 0.56 s); the 244,791-token prompt 816.8 / 45.0,
  draft 1564/2120 (73.8%). All inside the 0.1.57 floor (770–800, 909–948, 41–48). At 244K it is ~10% behind Q2_0
  (905.3 / 50.4), as the 1-bit pack was before.
- **Basalt's self-distilled MTP on UD-IQ1_M (2026-11-11).** The drafter now comes from
  `D:\GitHub\Strata-data\mtp\basalt-rt`: Basalt's `convert/mtp/rt/dense.bin` (116,099,072 bytes, SHA256 `DFE18647…`,
  a drop-in for the original `C724DC0B…`), with `experts.bin` and `draft_vocab.bin` hardlinked from `mtp\rt` and the
  same `dense.txt` (29 tensors, same offsets). Same 244,791-token prompt: **832.0 tok/s prefill, 47.0 tok/s decode,
  draft 1598/2115 (75.6%)** against 816.8 / 45.0 / 1564/2120 (73.8%) before — +4.4% decode, so it is kept. 55K cold
  draft 73/81 (90.1%) against 43/56 (76.8%). The pre-switch config is `strata-ud-iq1_m.bak-20261111-pre-basalt-mtp.json`;
  MTP is verified, so this is speed only, output unchanged.
- **A Vietnamese/code draft vocabulary (2026-11-11).** `--mtp-draft-vocab` now names
  `D:\GitHub\Strata-data\mtp\draft_vocab-vi-en-code.bin`: 65,568 int32 ids (262,272 bytes) converted from dongnhdev's
  `Qwen3.8-Flash-Next-draft-vocab-vi-en-code-64k.txt` (sha256 `F8B0DC7C…`), ranked over Vietnamese, English and code.
  The smaller draft head also frees VRAM: expert slots 2498 -> 2559 at the same `vram_free_mib` 1464. Same
  244,791-token prompt: prefill 831.7 tok/s, decode **51.5 tok/s**, draft 2219/2757 (**80.5%**) against 832.0 / 47.0 /
  1598/2115 (75.6%) with the shipped English/code subset — **+9.6% decode**. It drops most Japanese/Chinese ids (the
  old subset had 106,299); the old file stays at `mtp\rt\draft_vocab.bin`. The pre-switch config is
  `strata-ud-iq1_m.bak-20261111-pre-vi-vocab.json`.
- **Code test on UD-IQ1_M (2026-11-11).** Six focused tasks through the webchat path (`Origin` 8081,
  `reasoning_effort: high`, no tools): duration parser, merge intervals, top words, a JS `chunk`, the JS arrow fix and a
  JS off-by-one fix — **6/6 pass** against hidden tests run outside the model. The buggy car page alone (29 KB, not the
  900 KB mix): `finish=length` at `max_tokens` 16,384 in two runs (page cut at 10,260 chars); **32,768 finished in 350 s
  / 24,348 tokens**, the returned page parses under `node --check` and the missing `=>` is fixed. So a whole-page fix
  needs `max_tokens` 32,768 or empty with high thinking. The 244 KB mix still misdiagnoses (parallax), so the model is
  reliable on a focused file and not on a bug buried in a long context.
- **Vision moved to the GPU, elastic (2026-11-11).** The vision section was `"gpu": false` (CPU reader, 12 threads,
  1024 image tokens): a new picture took 10.1–10.3 s to read, a repeat 2.4 s. It is now `"gpu": true`, `"elastic": true`
  with the config's `"vram_elastic": true`: the encoder starts with the first picture (3.3 s, 1159 MiB of VRAM), a cold
  picture 6.8 s, a new picture with the encoder up 4.1 s, a repeat 2.4 s. While it is up the expert cache keeps 2048 MiB
  free (3072 of 3493 MiB left); text decode measured 49.9–50.3 tok/s against 51.3–52.1 with it down (noise). After 120 s
  without a picture it stops and the cache returns (3494 of 3493 MiB); slots stay 2559. `vram_free_mib` reads 1294
  instead of 1464 (above the 1024 floor). Accuracy: the two synthetic sets (14–16 px invoice/table text, shapes and
  text) 10/10 on the CPU and again 10/10 on the GPU, the Basalt banner 4/4 (the word, hexagons, one orange hexagon) —
  same answers on both devices. The 1024-token image cap stays. The code's owner note "the picture reader lives in RAM,
  not VRAM" is overridden on this PC only; the pre-switch config is `strata-ud-iq1_m.bak-20261111-pre-vision-gpu.json`.
- **UD-Q2_0 measured on 0.1.59.1 (2026-11-11).** `strata-ud-q2_0-tuned.json` was repointed to `build-v031` and given
  the same MTP (`mtp\basalt-rt`), draft vocabulary, `api_key` and `system_prompt` as IQ1_M; the router named it. Load:
  **2,407 expert slots**, 34.79 GiB of experts in RAM, `vram_free` 1462. The 244,791-token prompt: **prefill 825.6 tok/s,
  decode 46.9 tok/s, draft 1678/2197 (76.4%)** against IQ1_M's 831.7 / 51.5 / 80.5% — **IQ1_M is ~9% faster** at 244K.
  Short bench mixed (13K cold 48.9 vs 51.3, 55K cold 54.4 vs 52.1, 55K draft 38/39). The car page is misdiagnosed by
  both, so the 2-bit quality does not show in that test. Pre-edit config: `strata-ud-q2_0-tuned.json.bak-20261111-pre-run`.
  Same battery as IQ1_M: **6/6 code tasks pass** (duration 112.7 s / 6,325 tok, merge_intervals 14.0 / 659, top_words
  27.2 / 1,338, chunk 9.2 / 431, arrow fix 5.3 / 199, off-by-one 5.7 / 217 — about 174 s against IQ1_M's 263 s); the
  car page **419.0 s / 24,341 tok** (IQ1_M 350.6 s), parses under `node --check` and the `=>` is fixed. Quality is equal
  on this battery; Q2_0 is slower on the long page, as at 244K.
- **Merged v0.2.14.1 and built engine 0.1.60.1 (2026-11-16).** `build-v032\strata.exe` from the merged source
  (`.orca\build-v032.cmd`; the `strata_kq.dll` target is gone - the kernels link statically). Upstream's headline: the
  prompt experts run on Strata's own CUDA kernels (a build without `-DSTRATA_MMQ=ON`), and a long prompt on one card is
  cut into equal pieces. Measured here on UD-Q2_0 with MTP and the VI vocab: 244K prompt (236,310 tokens) **902-907 tok/s
  prefill against 825.6 (+9.3%), 46.8-49.4 tok/s decode against 46.9, draft 79-88% against 76.4%**; 55K cold 997-1006
  tok/s (1003), decode 52.6-53.5; 13K cold 802-834 (825.6), decode 44.5-53.7; cache re-read 35 tokens, first token
  0.59-0.61 s. Expert slots **2422** (2407); `vram_free` 1464. The Q2_0 config now also carries `STRATA_PCIE_BALANCE=1`
  (244K decode 46.8 -> 49.4 with it, the same direction as the IQ1_M A/B); `STRATA_Q2_BITPLANE` no longer exists in the
  0.1.60 source and `STRATA_HC_UPMIX=1` is an arch default, so neither is set by hand. Backup
  `strata-ud-q2_0-tuned.json.bak-20261116-pre-pcie-balance`. Kept through the merge: `kNativeFF = 2048` and the
  Q2_K trimmed down rows (moved to pq's `Tr::dot`/`from_float` and `row_size_of(kTQ8_K, ...)` - `ggml_vec_dot_t` and
  `GGML_TYPE_Q8_K` are gone), the q36 `kv8` FP16 KV path, Service profiles/`switch_model` (`/v1/load`), `strip_cjk`, the
  webchat guards (`_TOOL_HINTS`, `_ANSWER_CONTENT`, `without_content_tools`, the empty-answer retry), `mcp_note`,
  `answer_room_reserve`, `system_prompt`, `trusted_origins`. `supported_model()` now drops coder/nvfp4/swift names
  before the fork's `qwen3.8-*` pattern (upstream's new `test_drafting_file_fit` caught it). Upstream removed DeepSeek
  V4.1-Flash entirely (184 dsv41 files, the engine, docs and setup block; 242 files deleted, none ours). The vision
  GPU-elastic block was missing from the Q2_0 config and is restored (`gpu`, `elastic`, `vram_elastic`; backup
  `strata-ud-q2_0-tuned.json.bak-20261116-pre-vision-gpu`). Gates: undefined names 0; `pytest -k drafting` 1 failure
  (`test_the_names_the_setups_write`, the same one fails on the pre-merge worktree); node drafting/split-app/ui-r3 all
  green; `npm test` 1542 pass, 2 EPERM-symlink failures (Windows permission, not the code). Prod: router 8081 and
  `https://pc-dik-win.tail1b3f7b.ts.net:8443/` answer 200, `Origin: http://127.0.0.1:8081` + `strata_mcp` answered 3/3,
  an unknown origin gets 403.
- **Monitor: an effort tag on every request (2026-11-16).** `serve/server.py` records `effort` in the request history
  (`off` when thinking is off, else the client's `reasoning_effort`, or `budget N` for an Anthropic thinking budget);
  `serve/web/app.js` draws it beside the status badge in Recent requests. Qwen3.8-Flash-Next's `chat_template.jinja`
  supports **xhigh (the default), medium and low**, and maps `high` to `xhigh`, so the webchat's High is the top level
  and `none` is thinking off; there is no separate high behavior to show.
- **Merged v0.2.15 (2026-11-17).** Control 0.1.61, app and Terminal 0.2.15; **every engine package stays 0.1.60** — the
  release changes no engine code (only three `*_test.cpp` files build on MSVC), so prod keeps
  `D:\GitHub\Strata-data\build-v032\strata.exe` (0.1.60.1, LastWriteTime 11-16 09:45, unchanged by this merge); the
  merged `CMakeLists.txt` says 0.1.61 and that is a label only. What it brings: a saved Drafting choice survives a
  restart (`keep_saved_word` in `strata_cli/launch/runner.py`, reads `launch/<name>.json`), and Off too; on a card
  measured slower (sm_86) DFlash2 is no longer the stand-in for a chosen MTP (`runnable` in `drafting.decide`:
  `asked != "dflash2" and auto_mtp_only(...)`); Off fetches no draft layer; the installer puts the engine before setup on
  a PC with none (pictures stay on); the app never starts llama.cpp's `llama-server`; #6055 a stop without
  `--shutdown-timeout` answers 503 `server_draining` instead of accepting a request and cutting it at 0 tokens; #5979 a
  declared boolean written `True`/`False` is the boolean (a string argument is untouched); #5080 the About card's MTP
  line only when the MTP is the drafter; Monitor energy counts the GPUs that report power (#6012); chat notifications
  (#5617) and the parked-message fix (#5806); Linux AMD packages bundle `libatomic.so.1`; launch keeps a key that only the
  Access highlight made off "This computer only" (#5812). Kept through the merge: the `_SLOWER`/`MEASURED_SLOWER` rule,
  `_FORK_QWEN38_NAME` + `_EXCLUDED_NAME` (upstream's `supported_model` still takes only `_SUPPORTED_NAME`),
  `kNativeFF = 2048` and the Q2_K trimmed rows, q36 `kv8`, profiles/`/v1/load`, `strip_cjk`, the MCP/webchat guards,
  `system_prompt`, `trusted_origins`, the Monitor `effort` tag. `_FORK_QWEN38_NAME` now takes only the Unsloth UD sets
  (`qwen3.8-flash-next-ud-q2_0`) and this PC's old id (`qwen38-ud-iq1_m`), not every `qwen3.8-*`: that clears the last
  pytest failure. Gates: undefined names 0; `pytest -k drafting` **361 passed, 1 skipped, 0 failed**; node
  drafting/split-app/ui-r3 48/48; `npm test` only the two EPERM-symlink failures. Prod after restart: 2422 slots,
  `drafting=mtp`, `vram_free_mib` 1464, `cvec project:4-44`; the tuned config was not rewritten (mtime still 11-16).
  Bench on the same 0.1.60.1 binary: 13K cold 862, 55K cold 1017, cache re-read 35 tokens / first token 0.58 s, 244K
  (236,310 tokens) prefill 913-915 / decode 43.1-45.5 with draft 65.6-81.8% (yesterday's 902-907 / 46.8-49.4 at 79-88%
  is the same bytes: the decode spread follows the draft acceptance). Router 8081 and tailnet 8443 answer 200, trusted
  origin + `strata_mcp` 2/2, unknown origin 403. Branch and tag `backup-pre-0.2.15` / `backup-pre-0.2.15-tag`.
- **MTP and the VI draft vocabulary verified on prod (2026-11-19).** The engine log (the config's `"log"`) prints
  `strata mtp: draft layer loaded, 859 MiB of VRAM (experts 675, dense 111)`, `strata mtp: draft head over 65568 tokens
  (131.3 MiB)` and `strata mtp: --mtp-q4: draft head over 65568 tokens as Q4_0 (90.0 MiB read per step, was 131.3)`.
  **65,568 ids is `mtp\draft_vocab-vi-en-code.bin`** (262,272 B / 4) - the shipped English/code subset is 106,299 and
  the whole head 151,936 - so the tuned drafter, its vocabulary and `--mtp-q4 all` are all applied. The config's `"log"`
  had pointed at `D:\GitHub\Strata\strata-ud-iq1_m.log` (a stale IQ1_M path, which is where this proof was found);
  since 2026-11-19 it writes `%LOCALAPPDATA%\strata-stack\qwen-engine.log` (backup
  `strata-ud-q2_0-tuned.json.bak-20261119-pre-engine-log`). Bench that day on 0.1.60.1: 13K cold 813-834, 55K cold
  997-1014, cache re-read 35 tokens / 0.55-0.64 s, decode 46.7-53.9; a Vietnamese+code prompt (296 in, 320 out) drafted
  77.8%. The "slower" feeling is not the drafter: the recent rows are 100K-110K-token contexts at
  `reasoning_effort: high` with 378-1402 output tokens a turn (~8-31 s), the engine serves one request at a time, and a
  restart drops the conversation cache (the next turn re-reads the whole context).
- **The "unc" switch is the refusal-direction vector, not an adapter (2026-11-12).** The Chat drawer's "Bỏ kiểm duyệt
  (Uncensored)" toggle is `experimental_speed_projection` (`--control-vector-scaled ...experimental-speed-projection.gguf`),
  a control vector on layers 4-44 - there is no LoRA/adapter code in `serve/server.py`, and no "unc" adapter exists. It is
  loaded (`/metrics` engine `cvec=project:4-44`) and on for every request (`projection=true`), including the OpenCode
  session's. A/B on UD-Q2_0 with greedy sampling: scale 1.0 and 0.0 give different text, so it does act on this quant;
  scale 2.0 gave token-identical text to 1.0. Its 0/40 refusal measurement used harmful prompts on the OrcaUncensored Q2_K
  fit, not Unsloth UD-Q2_0: **IP/copyright refusals are a separate behaviour** - asking it to clone a game from another
  game's assets is still refused with the vector at 1.0. In the 93-request OpenCode session (60-79K context) there were no
  real refusals; 17 of 35 answers carried no text (thinking plus tool calls only), the 2-bit long-context pattern.
- **UD-Q2_0 now uses the model card's sampling (2026-11-11).** The `"sampling"` block (temperature 1.0 / top_p 0.95 /
  top_k 20) was removed from `strata-ud-q2_0-tuned.json` so the server's `MODEL_CARD_SAMPLING` decides per thinking
  state: thinking 1.0 / 0.95 / 20, instruct 0.7 / 0.80 / 20 + `presence_penalty` 1.5 (min_p 0, repetition_penalty 1.0
  in both) — Unsloth's recommended settings. `/props` reports 1.0 / 0.95 / 20, the startup line "sampling defaults from
  the config" is gone, and the server was restarted. Config backup: `strata-ud-q2_0-tuned.json.bak-20261111-pre-default-sampling`.
  IQ1_M and the v144 config still set temperature 0.3, which overrides both states.
- **A rule the model reads first (2026-11-11).** `system_prompt` in `strata-q2_0-v144-refusal.json` is prepended as the
  first `system` message of every request, whoever the client is: `Service.with_system_prompt` in `serve/server.py`,
  applied in `encode_prompt`, so webchat, OpenAI, Anthropic, Responses, MCP rounds and token counts all get it. The
  webchat's own System prompt comes after it; a conversation that already starts with the same text is not doubled. The
  text is the "check your own work before answering" rule (read code back, name the exact line, never claim a test you
  did not run). A model switch reads that config's rule (`profile_state` / `_apply_profile`). Absent or empty = the old
  prompt, byte for byte.
- **Webchat system prompt (2026-11-11).** Chat settings → System prompt (`#s-system` in `serve/web/index.html`,
  `settings.system` in `serve/web/app.js`) is sent as a `system` message of every chat request, after the server's
  `system_prompt` rule. It is per
  browser/origin (localStorage), not in the server's shared settings; empty = no custom prompt. The API itself
  already takes a `system` message (OpenAI) or a top-level `system` (Anthropic).
- **Runtime merge-loss gate (2026-11-10).** A merge can keep a call and drop its `def`: Python compiles and the
  failure only appears at runtime. That is how `63cf42a5` ("Merge v0.2.10", 2026-11-03) removed `def mcp_note`
  from `serve/server.py` while `anthropic_events` still called it — `/v1/messages` with server-side MCP raised
  `NameError` until `ce02ff67`. `.orca/undefined_names.py` lists calls to names bound nowhere in the module; it
  accepts directories (`python .orca/undefined_names.py serve strata_control strata_cli`) and must print
  `0 suspicious call(s)` before a merge is done. After a merge, also check `def mcp_note` and
  `answer_room_reserve` exist.
- **The numbers are the floor.** Measured 2026-11-06 with `.orca/bench-pack-ab.py` on this PC: UD-IQ1_M prefill
  770–800 tok/s (13K) and 909–948 (55K), cache first token 0.6–0.7 s, decode 41–48 tok/s, no "below 1024 MiB" line.
  Q2_0 with the same bench: 816 / 1003 and 48.6-55.7. A merge must keep or beat these. A number that went down means the
  merge changed behaviour: find the line that did it, fix or revert it, then merge again. Never ship "everything broke".
  On engine 0.1.60.1 (2026-11-16, `build-v032`) UD-Q2_0 measured 802 (13K cold), **1006** (55K cold) and **902-907
  prefill / 46.8-49.4 decode at 236K** - the long row is above 0.1.59.1's 825.6 / 46.9, and the 13K 802 is inside the
  IQ1_M band, so the floor stands.
- **How to check, in order:** `python -m pytest tests/terminal -k drafting` - **0 failed** is the bar now (2026-11-17:
  361 passed, 1 skipped; the old `coder-iq1_m` / `test_the_names_the_setups_write` failures are gone); `node --test
  tests/drafting.test.mjs tests/split-app.test.mjs tests/ui-r3.test.mjs` in `apps/host` - all green (48/48 on
  2026-11-17); full `npm test` in `apps/host` - only the two EPERM-symlink failures (chat-shell #4783, model-directory;
  Windows permission, not the code) may stay, nothing new; then restart the engine,
  run `.venv\Scripts\python.exe .orca\bench-pack-ab.py strata-ud-q2_0-tuned.json`, and send one chat call with
  `Origin: http://127.0.0.1:8081` and `"strata_mcp": true` - it must answer; an unknown origin must still get a 403.
- **The rule for the next custom change:** put every local speed or behaviour change in one place (Python's table or the
  run config), let the app read it from Control, and write it here. Never a third copy a merge can silently drop — that
  is exactly how this PC lost its speed on 2026-11-06.

## Merge checklist — follow every upstream merge, in order

A merge is done only when every box is checked. Skip nothing because "it probably still works".

### Before merging

- [ ] `git status` clean or committed; create a backup ref: `git branch backup-pre-<ver>` (and tag it).
- [ ] Write down the current version line (top of this file) and the engine binary version
      (`engine/strata.exe --version` or the serve log's `engine started` line). Merges do NOT rebuild the engine —
      the prebuilt binary stays whatever it was; note if upstream shipped a new engine package.
- [ ] `git fetch upstream --tags`; read `git log HEAD..upstream/main` and the release notes for anything touching
      `strata_control/drafting.py`, `serve/`, `strata-ud-iq1_m.json` consumers, the expert cache, or the flags in
      `.orca/tok-speed-playbook.md` section 12.

### During the merge

- [ ] Merge `upstream/main` (or the release tag) into `windows-coding`; resolve conflicts keeping the local
      behaviour above — when upstream and local disagree on speed/behaviour, the local tuned behaviour wins unless
      the upstream change is measured faster here.
- [ ] Confirm every item in the local-changes list above still exists in the merged tree (grep for `_SLOWER`,
      `dflash2Slower`, `STRATA_PCIE_BALANCE`, `trusted_origins`, `expert_profile_save`, `strip_cjk`,
      `_TOOL_HINTS`, `mcp_note`, `answer_room_reserve`).

### After merging — gates, in this order

- [ ] `python .orca/undefined_names.py serve strata_control strata_cli` — 0 suspicious calls. A merge that keeps a
      call and drops its `def` compiles clean and only fails at runtime: `63cf42a5` (v0.2.10) dropped `mcp_note`
      and `/v1/messages` + server-side MCP raised `NameError`.
- [ ] `python -m pytest tests/terminal -k drafting` — only the six known `coder-iq1_m` failures may remain.
- [ ] `cd apps/host && node --test tests/drafting.test.mjs tests/split-app.test.mjs tests/ui-r3.test.mjs` — all green.
- [ ] `cd apps/host && npm test` — only the four known old failures (chat-shell #4783, model-directory,
      ui-do file actions, markdown-crlf); nothing new.
- [ ] Re-read the tuned run configs — a merge or a Models-screen Save can write old numbers back:
      `strata-ud-iq1_m.json` keeps `drafting:"mtp"`, `--vram-reserve-mib 1472`, conversation cache
      10078/6/8000/1536, `expert_profile_save`, `trusted_origins`, `allowed_hosts`, and `env`
      `STRATA_EXPDEC=1 STRATA_PLE_AUTO_MMAP=1 STRATA_HC_UPMIX=1 STRATA_Q2_BITPLANE=1 STRATA_PCIE_BALANCE=1`;
      `strata-q2_0-v144-refusal.json` unchanged apart from upstream-needed fields.
- [ ] Kill ALL `strata.exe` / `strata-vision.exe` / `serve/server.py` first (duplicates once cut the expert cache
      to 1083 slots and decode to ~15 tok/s — that was NOT a merge regression). `nvidia-smi` must show ~12 GB free
      before starting exactly one server.
- [ ] Start the production config on 18080, wait for `/v1/models`, then check `/metrics`: correct model id,
      `drafting=mtp`, `spec=12`, expert slots at the full count for that pack (UD-IQ1_M ~2210, Q2_0 ~3176),
      `vram_free_mib` ~1464–1472, no "below 1024 MiB" line in the log.
- [ ] `.venv\Scripts\python.exe .orca\bench-pack-ab.py <prod-config>` — compare against the floor numbers above
      (and the Q2_0 row). A number that went down means the merge changed behaviour: find the line, fix or
      revert it, re-merge. Never ship "everything broke".
- [ ] One chat call through the router with `Origin: http://127.0.0.1:8081` and `"strata_mcp": true` — must
      answer; an unknown origin must still get 403.
- [ ] Router on 8081 and `https://pc-dik-win.tail1b3f7b.ts.net:8443/` both answer 200; `/v1/models` shows the
      production model id.
- [ ] If `model-router.py` changed upstream-side, re-sync the deployed copy at
      `%LOCALAPPDATA%\strata-stack\model-router.py` with `.orca/local-stack/model-router.py` and restart the router
      (`run-router.bat`). Its `QWEN_CFG`/`QWEN_ID` must name the production config.
- [ ] Update the version line at the top of this file and any moved floor numbers; commit the merge and push
      `windows-coding`.

### Things that are NOT the merge's fault (check before blaming it)

- Duplicate engines on the GPU (expert slots ~1083, decode ~15–20 tok/s) — kill extras, restart once.
- `--mmap-experts` or too little free RAM (~33 GiB needed) — expert arena won't fit, file-tier reads, decode ~20.
- The Models screen in the app overwriting the tuned config on Save.
- Q2mix/UD-IQ1_M tool-call stops are a model property, not a regression — Q2_0 is the agentic choice.

## Contributing a change or report

The rules are in **[CONTRIBUTING.md](CONTRIBUTING.md)**. Read it before you open an issue or a pull request, and
follow it whether a person or an agent writes the text. The short version:

- Start every issue and pull request title with its area: `[Engine]`, `[GUI]`, `[TUI]`, `[Benchmark]`, `[Docs]` or
  `[Other]`, for example `[Engine] fix …`. A check on GitHub fails a pull request whose title has no area.
- Search the open and closed issues and pull requests first, and add to a thread that already covers your point.
- Agree the scope in an issue before a large feature, a refactor or a change to a default.
- One problem per pull request. Lead with the problem and the result, then the approach, then the validation
  (passed, failed and not run, kept apart) and the limits.
- A new feature is opt-in, and the default path stays byte-identical to the last release. Say how you checked.
- Build every backend a file touches (CUDA, HIP, SYCL) before asking for review.
- Change a default only where you measured it faster, and show the numbers with what they were measured on.
- Never submit measurements, logs or reproduction steps you did not produce. Mark a finding from reading code as
  unconfirmed static analysis.
- A report from hardware the maintainers do not have is welcome. Follow
  [docs/COMMUNITY_BENCHMARKS.md](docs/COMMUNITY_BENCHMARKS.md), compare against a same-day run of the build you are
  testing, and say what you did not test.
- Open test requests and the hardware that is wanted are listed in [docs/TEST_REQUESTS.md](docs/TEST_REQUESTS.md).
