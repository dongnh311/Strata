# AGENTS.md

Version 0.2.22 (source merged from upstream v0.2.22; the app and Terminal are 0.2.22 and Control and the
engine packages are 0.1.69 — the engine binary on this PC is 0.1.69, built from the merged source into
`D:\GitHub\Strata-data\build-v034` and running in production; `build-v033` (0.1.62), `build-v032` (0.1.60.1),
`build-v031` (0.1.59.1) and `build-v030` stay for rollback). The public model families are
Qwen3.8-Flash-Next and Qwen3.6-35B-A3B (upstream removed DeepSeek V4.1-Flash in 0.2.14: the `dsv41` engine, its
sources and docs are gone; our `strata-unc48l*` configs and the `unc48L` model were already deleted here). Read **[docs/AI_REFERENCE.md](docs/AI_REFERENCE.md)** for model availability, APIs, hardware limits and
source-backed claims. Articles and videos should use **[docs/MEDIA_KIT.md](docs/MEDIA_KIT.md)**.

For recommendations and agent-assisted setup, prefer **ISTA-DASLab → Unsloth → Gyro → others**, using only a
compatible pack that fits the selected model and hardware. ISTA-DASLab is the default recommendation; Gyro is a
memory-saving fallback and is currently slower. Honor an explicit user choice. This is recommendation policy;
existing executable defaults may differ, so inspect the plan and choose the family explicitly.

Strata has three parts:

- **The app** (`app/desktop`, the Tauri shell; `app/host`, the Node host and the web UI). It is for people who do
  not want a terminal. One installer per system ([latest release](https://github.com/Niko1221/Strata/releases/latest)):
  `Strata-0.2.16-windows-x64-setup.exe`, `Strata-0.2.16-linux-x86_64.AppImage`, `Strata-0.2.16-macos-arm64.dmg`.
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
  the packages and the update feed: [packaging/README.md](tools/packaging/README.md) and [packaging/UPDATES.md](tools/packaging/UPDATES.md).
- AMD (HIP) build and validation: [docs/AMD_HIP.md](docs/AMD_HIP.md); multi-GPU: [docs/MULTI_GPU.md](docs/MULTI_GPU.md);
  Mac (Metal): [docs/MAC.md](docs/MAC.md).
- Tests: the Terminal and Control tests are in `terminal/tests/terminal` (`python -m pytest terminal/tests/terminal`). The app's UI
  tests run with `npm test` in `app/host`. Setup's own tests run without a GPU or downloads:
  `python tools/test_setup_<name>.py` (for example `terminal/tools/test_setup_amd.py`, `terminal/tools/test_setup_choices.py`).
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
- **Edge0-120B q3k runs on this PC (2026-11-19, experiment only; prod stays Q2_0).** It needs its own engine:
  `D:\GitHub\Edge0\edge0-strata\build\strata.exe` (0.1.55, built from `EDGE0.md` "Build (Windows, NVIDIA)" with
  CUDA 13 sm_86 and the pinned ggml `3cf03257`) and `D:\GitHub\Edge0\edge0-infer\build\windows\bin\edge0-infer.exe`
  (preset `windows`); the model is `D:\GitHub\Edge0-data\Edge0-120B-q3k` (84 GiB, `latent_dense_q8.bin` skipped:
  Windows defaults to `du=q4`). `edge0-infer` ran with `--strata-dir D:\GitHub\Edge0\edge0-strata
  --strata-python D:\GitHub\Strata\.venv\Scripts\python.exe --context 32768 --port 8000
  --strata-arg --vram-reserve-mib --strata-arg 1024` (the Strata venv already has numpy 2.5.3/psutil/snapshot pins).
  On the 12 GB card - below Edge0's stated 16 GiB minimum - the engine still started: **882 expert slots (979 MiB of
  VRAM), arena 27,300 MiB (26.66 GiB of experts in RAM), vram_free 936 MiB, spec 6, kv int8, pcie_frac 0.55**.
  Measured through its OpenAI API: 4K prompt 278.8 tok/s prefill (15.9 s) / 18.0 tok/s decode; 12K 325.5 tok/s
  (40.6 s) / 22.3 tok/s; cache re-read 7 tokens, first token 0.23 s; a Vietnamese CSV code answer 244 tokens at
  26.8 tok/s; a declared `get_weather` tool call answered `finish=tool_calls` with `{"city":"Hanoi"}` in 4.4 s. Compare
  Q2_0 on the same PC: ~1000 tok/s prefill and 47-54 decode, 262K context, vision. `edge0-infer` was stopped and prod
  restored (`StrataRestart` + `/v1/load`, 2422 slots, vram_free 1464). Q2_0 was unloaded with `POST /v1/unload`
  (key + trusted Origin) because `serve` has `auto_load`; any request would have reloaded it over Edge0. Keep or delete
  `D:\GitHub\Edge0` and `D:\GitHub\Edge0-data` (84 GiB) as the owner decides.
  **Made usable (same day):** `D:\GitHub\Edge0-data\start-edge0.ps1` (unloads Q2_0 with `/v1/unload`, waits for
  10 GiB free, starts `edge0-infer` detached with `--context 65536 --kv-resident 32768 --mtp-q4 all
  --vram-reserve-mib 1024`, prints the metrics) and `stop-edge0.ps1` (stops the fork's processes by path, runs
  `StrataRestart` + `/v1/load`, waits for Q2_0). At 64K: **799 slots**, 936 MiB free, 4K 279.2 tok/s prefill /
  17.8 decode, 12K 317.1 / 18.6, cache 7 tokens / 0.27 s first token - decode is the same as 32K, so 64K is the default.
  OpenCode has a provider `edge0-local` (`http://127.0.0.1:8000/v1`, model `edge0_120b`, context 65536, output 8192,
  reasoning low; backup `opencode.json.bak-20261119-pre-edge0`): `opencode -m edge0-local/edge0_120b` answered, but its
  ~8K-token system prompt costs ~29 s of prefill at ~280 tok/s. Keep Q2_0 as the running default; while Edge0 runs, use
  port 8000, not the 8081 webchat (the 18080 server is unloaded but alive and `auto_load` would try to reload Q2_0).
  **Strata's tuning on Edge0 (2026-11-19):** `STRATA_PCIE_BALANCE=1`, `STRATA_EXPDEC=1`, `STRATA_PLE_AUTO_MMAP=1`,
  `--mtp-q4 all`, `--mtp-draft-vocab D:\GitHub\Strata-data\mtp\draft_vocab-vi-en-code.bin`, `--kv-resident 32768`,
  `--conversation-cache-mib 2048 --slots 2 --min-free-mib 1024`, `--short-read 128`, `--prompt-cache-spread`,
  `--pool-workers 20` (24 warns: the i7-14700K has 20 physical cores). The template now carries
  `"log": "D:/GitHub/Edge0-data/edge0-engine.log"`; it prints **`strata mtp: draft head over 65568 tokens (170.1 MiB)`**
  and the Q4_0 copy at 90.0 MiB/step - the VI vocabulary is applied to Edge0's own MTP. At 64K: **894 slots**,
  4K 278.4 tok/s prefill / 16.7 decode, 12K 318.0 / 25.2, cache 7 tokens / 0.33 s. At **256K** (`--context 262144`,
  `--kv-resident 32768`): 819 slots, `vram_free` 676 MiB, a 236,042-token prompt **201.4 tok/s prefill (1,172 s) /
  19.1 decode / draft 50%**, against Q2_0's 902-915 / 46.8-49.4 at 236K - Edge0 is **4.5x slower to prefill and 2.4x to
  decode** once the KV streams from host RAM; the same 180,062-token needle at depth 50% **passed on both** (Edge0
  205.6 tok/s / 877 s, Q2_0 932.6 / 194 s). So 64K is Edge0's practical mode and Q2_0 stays the daily driver.
  **Deleted later the same day (owner's call):** `D:\GitHub\Edge0` and `D:\GitHub\Edge0-data` removed (85 GB
  back: D: free 144 -> 229 GB), the `edge0-local` OpenCode provider removed (config restored from
  `opencode.json.bak-20261119-pre-edge0`), and Q2_0 back as the only model (2422 slots, `vram_free` 1464, a webchat
  `Origin` call answered, 8443 answers 200). The report and the small scripts stay at
  `D:\GitHub\Strata-data\edge0-notes\` (`REPORT.md`, `start-edge0.ps1`, `stop-edge0.ps1`, `bench-edge0.py`,
  `bench-edge0-256k.py`, `needle.py`, `vi-test.py`).
- **UD-Q2_0 against the Mac's DS4-IQ2 (2026-11-19, measured).** The same 12 short questions (arithmetic, logic,
  code trace, string reverse), `temperature 0`, `reasoning_effort: high`, ~150-token prompts: **PC 12/12 in 71 s,
  Mac 12/12 in 94 s**. The PC's only "miss" was `atar ts` for `strata` reversed - the right string with a space in
  it, a tokenization artifact, so both are 12/12. The same questions at the end of a **55,432-token** page answered
  **12/12 in 76 s on the PC with `--kv q4_0`**, so 55K and 4-bit KV do not break reasoning. So "the Mac feels
  smarter" is not a reasoning gap at these lengths; and `ivanfioravanti/Qwen3.8-Flash-Next-DS4-IQ2` is not a 2-bit
  peer: `lm_head`/dense/shared **Q8_0**, embeddings **BF16**, gate/up **IQ2_XXS** with Unsloth's imatrix, and a
  **Q4_1 PLE sidecar of 29.8 GiB** - 71.5 GiB in total against UD-Q2_0's 65.7 GiB. It also only runs on
  `ds4-metal` (its 48 down tensors are **zero-padded 640 -> 768 columns**; commit `5bd8796` or later, "compatibility
  with other runners is not claimed"), so it cannot load in Strata here at all. Its own author measured the current
  build **worse** than his previous 2-bit one: NLL 0.290735 -> 0.303570 (+4.4%), top-token 91.33% -> 90.32%,
  hard-smoke 6/12 -> 5/12. Scripts: `D:\GitHub\Strata-data\ab-quant.py`, `ab-longctx.py`; rows in `ab-quant-*.json`.
  The same day, the long-file battery (`ab-filefix.py`, a 29 KB page with one `=>` deleted, `max_tokens` 32768,
  graded by `node --check` and the restored arrow): **PC PASS in 339 s / 24,341 tokens, Mac PASS in 346 s / 16,153
  tokens**. The PC returned the input byte for byte apart from the fix; the Mac also repaired a mangled em-dash in
  the title. So the PC is not weaker on a whole-file edit either, and needs more output tokens for the same result.
  The Mac has to be called with `"stream": true`: Cloudflare cuts a non-streaming origin at 100 s
  (`edge_deadline_exceeded`), so a 5-minute answer can only come back over SSE.
- **Merged v0.2.22 and built engine 0.1.69 (2026-11-26).** App and Terminal 0.2.22; Control and every engine
  package 0.1.69. `D:\GitHub\Strata-data\build-v034\strata.exe` is that engine, built by `.orca\build-v034.cmd`
  (the same flags as v033: `-S engine`, the vendored `third_party/strata-ggml`, no MMQ), and **prod runs it** (the
  pre-switch config is `strata-ud-q2_0-tuned.json.bak-20261126-pre-v034`, and `build-v033` is the rollback). 977
  upstream commits, 1,594 files, +320,361 / -17,095. The 32 conflicts: `AGENTS.md` and the fork's text kept; the 18
  locale catalogs taken from 0.2.22 with `tool.rejected` and the guic77 clause re-added; `server.py` 10 hunks (the
  `/v1/load` profiles and switch, `system_prompt`, `strip_cjk`, `without_content_tools`/`empty_answer_*`/
  `answer_room_reserve` all kept beside upstream's Hy4/Inkling stop tokens, key limits, image prompt tokens,
  `has_vision()` and `/v1/models` shape); `drafting.py` keeps `_SLOWER`/`MEASURED_SLOWER` and adds upstream's
  canonical-pack rule (#7090); `app.js`/`index.html` keep the System prompt field and the model guard and take
  `thinkingForFamily`; the two workflow files stay deleted. **Upstream rewrote the q36 K/V cache**
  (fp32/fp16/fp8/fp4): the fork's q36 `kv8`/Q8_0 patch is gone; `--kv q8_0` parses as fp8 and `q4_0` as fp4, and
  nothing this PC runs uses the q36 engine. Upstream also added its own `vec_dot_q2_K/q3_K`, `dq_q2_k` and
  `Fmt<10>/<11>`, so the fork's duplicate definitions were dropped; the Q2_K trimmed-row code (`q2k_dot`,
  `row_dot_q2k_trim`, `Q2K_HALF_BYTES`, and `trimmed_row_bytes` in `gguf_reader.hpp`, restored after the
  conflict) stays, and `prefill.cpp` keeps `iq_dequant_rows_f16` with upstream's `gu_type == kNvfp4` guard;
  `kNativeFF = 2048` unchanged. `has_vision()` now includes the fork's `native_vision` (dsv41). The Inkling and Hy4
  parsers take the fork's `aliases` keyword too: the merge passed it from `_run` to every parser class, so the launch's
  `max_tokens: 1` readiness probe got a 400 (`InklingOutputParser.__init__() unexpected keyword argument 'aliases'`);
  fixed in `frontend.py` (`JsonOutputParser`, `Hy4OutputParser`, `InklingOutputParser`). Two SYCL-mount
  tests skip on this PC (they assume no `Strata-data` beside the checkout), with the reason in the test.
  **`STRATA_PF_SMALL=0` is in the tuned config**: 0.2.22's small-card rule fired (expert cache 2337 slots, default
  chunk 7936 < 8192) and picked the small-card prompt path, which cost 5% at 13K and 4% at 55K; the numbers below
  use the default path. Gates: undefined names 0; `pytest terminal/tests/terminal -k drafting` **450 passed, 2
  skipped, 0 failed**; node drafting/split-app/ui-r3 **48/48**; `npm test` **2,388 tests, 2,238 pass, 2 fail**
  (only the two EPERM-symlink ones). Bench against a same-day 0.1.62 run (the card was slower today than on
  20/11, so only the same-day pair compares): 13K cold **854** (0.1.62: 846), cache **35 tokens read, first token
  0.59 s** (0.70), 55K cold **1013** (1000), decode 42.1 / 42.4 / 43.0 / 40.4 (40.2 / 42.5 / 42.7 / 46.8); the
  234,300-token prompt read 213,021 tokens in 235.2 s (**906 tok/s**, 0.1.62: 893) with decode 40.0 (39.7). Prod
  after the switch: **2337 slots, `drafting=mtp`, `kv q4_0`, `vram_free_mib` 1542, `cvec project:4-44`**, and the
  log's `draft head over 65568 tokens` and `--mtp-q4` Q4_0. Branch and tag `backup-pre-0.2.22` /
  `backup-pre-0.2.22-tag`.
- **Inkling-2-Mini SQ-10 abliterated on this PC (2026-11-26).** `SC117/Inkling-2-Mini-abliterated-Strata` SQ-10 +
  Vision (11.14 GB, 146 s) in `D:\GitHub\Strata-data\models\Inkling-2-Mini-abliterated` (pack hash matches the repo);
  `strata launch --model-path ... --model sq-10 --family inkling-2-mini --context 32k --vision on --port 8000` installs
  `strata-inkling` 0.1.69 (419 MB) and serves it. **The Inkling engine has no control-vector code**, so the Qwen
  `experimental-speed-projection` vector cannot be applied to it; the abliterated pack is the unc equivalent (rank-1
  orthogonal ablation of `attn.wo_ud`, layers 4..23, 20 tensors, scales 4.0/2.5; the author's 10-prompt audit R=0;
  SQ-10 agrees with the original on 92.35% of next tokens). On the RTX 3060 (SQ-10, 32K, `--kv fp8`, KV auto-offloaded
  to host, DSpark on): ~25 s to load, 11.2 GiB VRAM, 1.03 GiB host expert arena + 1.0 GiB host KV; prefill 509 tok/s
  at 2,053 tokens and 696-764 at 8-32K; decode 41.9 tok/s at 2K, 19.6 at 8K, 11.6 at 16K, 9.3 at 24K, 7.2 at 32K (the
  KV reads come from host RAM); a 16K repeat reused 16,213 tokens, first token 0.37 s; tool call
  `get_weather({"city":"Hanoi"})` and vision ("42, circle") correct; three harmless fiction/rudeness probes all answered.
  `--kv-offload off` at 16K makes the engine shrink the context to 4,864 to keep KV in VRAM. Bench scripts:
  `.orca/bench-inkling.py`, `.orca/bench-inkling-ladder.py`, `.orca/bench-inkling-port.py`. The launch also adopted the
  old root run configs and launchers into `terminal/` (every `strata-*.json` and `run-*.bat` moved at 10:01), so the
  router now prefers `terminal/strata-ud-q2_0-tuned.json` and falls back to the root copy, and copies of the four
  active configs were put back in the root for the old scripts; `terminal/run-q2_0.bat` pointed at `terminal\.venv`
  (no such folder) and was fixed to the repo's `.venv`.
- **Inkling-2-Mini was tried and removed the same day (2026-11-26).** The stock SQ-10 pack (11.13 GB, hash checked)
  and the abliterated one (11.14 GB) were installed and served through a two-backend model-router v1.3 (Qwen 18080,
  Inkling 8000), then deleted on the owner's call: `models\Inkling-2-Mini-SQ-10`, `models\Inkling-2-Mini-abliterated`,
  `packs\inkling-2-mini-sq-10`, the `terminal\strata-inkling-sq10-*.json` run configs, the `inkling2` engine component
  and the saved `sq-10-*` launch profiles are gone (20.8 GB back). `.orca/local-stack/model-router.py` is the Qwen-only
  v1.2 again (the v1.3 source is in commit `03f432c25`; `.orca/local-stack/model-router.py.bak-20261126` is the
  v1.2 file that v1.3 replaced, so a future retry rebuilds v1.3 from that commit). The `profile_state` fix
  (`engine_args(cfg, exe)` in server.py, so a profile switch keeps `--vision`) stays — it is a real bug fix. The
  measured record: stock at 1M with `--kv k8v4` was **41.8 tok/s at 2K / 31.3 at 8K / 11.7 at 32K** (fp8: 40.4 / 26.8 /
  9.5), the 1M needle passed (1,047,456 tokens, `ORANGE-7421`, 2 h 42 min, 108 tok/s prefill, 0.1 tok/s decode), the
  `-fast` profile (KV in VRAM) 55.7-57.6 tok/s at 2.3K; it was still 4x slower than Qwen at long context because the
  loader caps the experts at 7.03 GiB (383 host + 6 SSD, CPU lane 24 ms/token) and the K/V lives in host RAM — a
  property of the 12 GB card and engine 0.1.69, not of the config. Qwen UD-Q2_0 stays the daily driver.
- **ISTA-DASLab IQ2_XS tried against UD-Q2_0 (2026-11-26).** `strata launch --model IQ2_XS --context 256k --vision gpu
  --drafting mtp` downloaded and prepared the ISTA pack (`models\IQ2_XS`, 63.4 GB, 2 shards; `packs\iq2_xs`), and its own
  server ran on 8080 with engine 0.1.57; the same pack was then served by `build-v034` (0.1.69) with the tuned Qwen
  config's flags (`--kv q4_0`, `--kv-resident 32768`, MTP `basalt-rt` + the VI draft vocab, `STRATA_PF_SMALL=0`,
  `STRATA_PCIE_BALANCE=1`): `terminal\strata-iq2_xs-tuned.json`. Measured with `.orca/bench-pack-ab.py` (13K/55K) and
  `.orca/bench-244k-one.py` (~199K): **3,041 expert slots against UD-Q2_0's 2,336**; prefill **812 / 953 / 880 tok/s
  against 854 / 1,013 / 906** (IQ2_XS 3-6% slower); decode **43.5 / 47.3 / 49.2 against 42.1 / 43.0 / 40.0** (IQ2_XS
  5-23% faster, the long row the widest); cache re-read 35 tokens / 0.58 s (UD-Q2_0 0.59). The ~199K needle passed
  (`ORANGE-7421`, the 198,783-token prefix fully reused on the repeat). Vision reads the test image ("42, a circle").
  The six-question battery: **IQ2_XS 5/6** (Wednesday + 100 days -> "Saturday"), **UD-Q2_0 6/6** ("Friday"); every other
  answer identical. Prod stays UD-Q2_0 until the owner decides; the IQ2_XS config is staged and its 8080 server is left
  unloaded (auto-load on a request).
- **Merged v0.2.16 and built engine 0.1.62 (2026-11-20).** App and Terminal 0.2.16; Control and every engine
  package 0.1.62. `D:\GitHub\Strata-data\build-v033\strata.exe` is that engine, built by `.orca\build-v033.cmd` from
  `-S D:\GitHub\Strata\engine` (own-stack: no llama.cpp MMQ options at all, ggml from the vendored
  `engine\third_party\strata-ggml`), and **prod runs it** (the tuned config's `exe`; the pre-switch config is
  `strata-ud-q2_0-tuned.json.bak-20261120-pre-v033`, and `build-v032`/v031/v030 stay for rollback). The release moved
  every top-level folder: `src/ include/ metal/ sycl/ CMakeLists.txt` → `engine/`, `serve/ strata.py strata_cli/
  strata_control/ tests/` → `terminal/`, `apps/` → `app/`, `data/` → `terminal/data/`; git's rename detection kept
  every local file. The 7 content conflicts (`AGENTS.md`, `app/host/server/native-settings.mjs`,
  `app/host/src/lib/drafting.ts`, `terminal/serve/server.py`, `terminal/serve/web/app.js`,
  `terminal/strata_cli/launch/runner.py`, `terminal/strata_control/drafting.py`) and the 5 files added inside moved
  folders (`serve/dsv41_vision.py`, `serve/test_cjk.py`, `serve/test_dsv41_vision.py`,
  `serve/test_model_switch.py`, `tests/terminal/test_launch_dsv41_overrides.py`) were resolved by hand.
  **Upstream split `server.py` into `terminal/serve/server_parts/`**: our local names stayed in
  `terminal/serve/server.py` and nothing under `server_parts/` imports them back (checked: no circular import), so the
  guards (`without_content_tools`, `empty_answer_*`, `answer_room_reserve`, `system_prompt_of`) and the local
  `load_tokenizer`/`model_profiles` (`/v1/load`, Service profiles) are still there, beside `mcp.py`'s `_TOOL_HINTS` and
  `_ANSWER_CONTENT`. **Prod paths had to move**: the run configs' `D:\GitHub\Strata\data\...` →
  `D:\GitHub\Strata\terminal\data\...` (`strata-ud-q2_0-tuned.json`, `strata-ud-iq1_m.json`,
  `strata-q2_0-v144-refusal.json`; the `.bak-*` keep the old path as the record), the router (`.orca/local-stack` and
  the deployed `%LOCALAPPDATA%\strata-stack\model-router.py`) now resolves `terminal/serve/server.py` with a fallback to
  `serve/server.py`, and `run-q2_0.bat` + `AI-Gateway-MLX\scripts\windows\run-strata-config.cmd` name the new path.
  This clone is now `core.autocrlf=false` — v0.2.16's tests match `\n`, and CRLF failed `shell-languages`,
  `agent-mcp-model-timeout` and `monitor-gpu-load-hint`; `app/desktop/src-tauri/src/shell.rs`,
  `terminal/serve/web/app.js` and `app/host/server/index.mjs` were converted to LF. Text this fork adds must be
  translated or the locale gates fail: `tool.rejected` was added to the 9 web catalogs and the draftingHint's card
  clause to the 9 `guic-*.json` (fr with its NBSPs). Gates: undefined names 0; `pytest terminal/tests/terminal -k
  drafting` **409 passed, 1 skipped, 0 failed**; node drafting/split-app/ui-r3 **48/48**; `npm test` **2022 pass, 2
  fail** (only the two old EPERM-symlink ones: chat-shell #4783, model-directory). Bench on build-v033 with the tuned
  config: 13K cold **849** tok/s (floor 802), cache **35 tokens read, first token 0.49 s**, 55K cold **1008** (floor
  1006), decode 45.3 (13K) / 49.9 (cache) / 50.8 (follow) / 54.5 (55K); 244K prompt (234,300 tokens) **901 and 879**
  tok/s prefill against 902-915 (the same bytes within the run spread), decode **46.2** against 43.1-49.4 — the first
  cold run gave 34.6, a cold-start outlier that the repeat did not reproduce; a warm-cache rerun gave 987 / 52.2 with
  21,279 tokens reused. Prod after the switch: **2422 slots, `drafting=mtp`, `kv q4_0`, `vram_free_mib` 1464, `cvec
  project:4-44`**, the webchat `Origin: http://127.0.0.1:8081` + `"strata_mcp": true` answered 200 (`finish=stop`), an
  unknown origin got 403, and the router 8081 and `https://pc-dik-win.tail1b3f7b.ts.net:8443/v1/models` both answered
  200 with `qwen3.8-flash-next-ud-q2_0`. Branch and tag `backup-pre-0.2.16` / `backup-pre-0.2.16-tag`.
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
  accepts directories (`python .orca/undefined_names.py terminal/serve terminal/strata_control terminal/strata_cli`) and must print
  `0 suspicious call(s)` before a merge is done. After a merge, also check `def mcp_note` and
  `answer_room_reserve` exist.
- **The numbers are the floor.** Measured 2026-11-06 with `.orca/bench-pack-ab.py` on this PC: UD-IQ1_M prefill
  770–800 tok/s (13K) and 909–948 (55K), cache first token 0.6–0.7 s, decode 41–48 tok/s, no "below 1024 MiB" line.
  Q2_0 with the same bench: 816 / 1003 and 48.6-55.7. A merge must keep or beat these. A number that went down means the
  merge changed behaviour: find the line that did it, fix or revert it, then merge again. Never ship "everything broke".
  On engine 0.1.60.1 (2026-11-16, `build-v032`) UD-Q2_0 measured 802 (13K cold), **1006** (55K cold) and **902-907
  prefill / 46.8-49.4 decode at 236K** - the long row is above 0.1.59.1's 825.6 / 46.9, and the 13K 802 is inside the
  IQ1_M band, so the floor stands.
- **How to check, in order:** `python -m pytest terminal/tests/terminal -k drafting` - **0 failed** is the bar now (2026-11-26:
  450 passed, 2 skipped; the old `coder-iq1_m` / `test_the_names_the_setups_write` failures are gone and the two
  SYCL-mount skips are this PC's layout); `node --test
  tests/drafting.test.mjs tests/split-app.test.mjs tests/ui-r3.test.mjs` in `app/host` - all green (48/48 on
  2026-11-26); full `npm test` in `app/host` - only the two EPERM-symlink failures (chat-shell #4783, model-directory;
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

- [ ] `python .orca/undefined_names.py terminal/serve terminal/strata_control terminal/strata_cli` — 0 suspicious calls. A merge that keeps a
      call and drops its `def` compiles clean and only fails at runtime: `63cf42a5` (v0.2.10) dropped `mcp_note`
      and `/v1/messages` + server-side MCP raised `NameError`.
- [ ] `python -m pytest terminal/tests/terminal -k drafting` - 0 failed is the bar (2026-11-26: 450 passed, 2 skipped).
- [ ] `cd app/host && node --test tests/drafting.test.mjs tests/split-app.test.mjs tests/ui-r3.test.mjs` — all green.
- [ ] `cd app/host && npm test` — only the two EPERM-symlink failures (chat-shell #4783, model-directory);
      nothing new.
- [ ] Re-read the tuned run configs — a merge or a Models-screen Save can write old numbers back:
      `strata-ud-iq1_m.json` keeps `drafting:"mtp"`, `--vram-reserve-mib 1472`, conversation cache
      10078/6/8000/1536, `expert_profile_save`, `trusted_origins`, `allowed_hosts`, and `env`
      `STRATA_EXPDEC=1 STRATA_PLE_AUTO_MMAP=1 STRATA_PCIE_BALANCE=1` (and, since 2026-11-26, `STRATA_PF_SMALL=0`);
      `strata-q2_0-v144-refusal.json` unchanged apart from upstream-needed fields.
- [ ] Kill ALL `strata.exe` / `strata-vision.exe` / `serve/server.py` first (duplicates once cut the expert cache
      to 1083 slots and decode to ~15 tok/s — that was NOT a merge regression). `nvidia-smi` must show ~12 GB free
      before starting exactly one server.
- [ ] Start the production config on 18080, wait for `/v1/models`, then check `/metrics`: correct model id,
      `drafting=mtp`, `spec=12`, expert slots at the full count for that pack (UD-IQ1_M ~2210; Q2_0 **2337** on
      0.1.69, 2422 on 0.1.62-0.1.60.1), `vram_free_mib` ~1464–1546, no "below 1024 MiB" line in the log, and no
      `small expert cache` line with `STRATA_PF_SMALL=0` set.
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

The rules are in **[CONTRIBUTING.md](.github/CONTRIBUTING.md)**. Read it before you open an issue or a pull request, and
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
