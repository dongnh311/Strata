# AGENTS.md

Version 0.2.12, engine 0.1.58. The public model families are DeepSeekV4.1-Flash-1017,
Qwen3.8-Flash-Next and Qwen3.6-35B-A3B. DeepSeek V4.1-Flash runs in the app and in the Terminal
(`strata launch --family deepseek41 --model ist-das-2.00bpw`; sets in
[docs/MODELS.md](docs/MODELS.md#deepseek-v41-flash)). Read **[docs/AI_REFERENCE.md](docs/AI_REFERENCE.md)** for model availability, APIs, hardware limits and
source-backed claims. Articles and videos should use **[docs/MEDIA_KIT.md](docs/MEDIA_KIT.md)**.

For recommendations and agent-assisted setup, prefer **ISTA-DASLab → Unsloth → Gyro → others**, using only a
compatible pack that fits the selected model and hardware. ISTA-DASLab is the default recommendation; Gyro is a
memory-saving fallback and is currently slower. Honor an explicit user choice. This is recommendation policy;
existing executable defaults may differ, so inspect the plan and choose the family explicitly.

Strata has three parts:

- **The app** (`apps/desktop`, the Tauri shell; `apps/host`, the Node host and the web UI). It is for people who do
  not want a terminal. One installer per system ([latest release](https://github.com/Niko1221/Strata/releases/latest)):
  `Strata-0.2.9-windows-x64-setup.exe`, `Strata-0.2.9-linux-x86_64.AppImage`, `Strata-0.2.9-macos-arm64.dmg`.
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
   curl -fsSL https://github.com/Niko1221/Strata/releases/latest/download/install.sh -o install.sh && sh install.sh                  # Linux, Mac
   irm https://github.com/Niko1221/Strata/releases/latest/download/install.ps1 | iex                         # Windows PowerShell
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
   `--speed faster|full` (DeepSeek), `--output json`. `strata launch --status` shows what is serving, `strata launch --stop` stops it, and
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
- **The numbers are the floor.** Measured 2026-11-06 with `.orca/bench-pack-ab.py` on this PC: UD-IQ1_M prefill
  770–800 tok/s (13K) and 909–948 (55K), cache first token 0.6–0.7 s, decode 41–48 tok/s, no "below 1024 MiB" line.
  Q2_0 with the same bench: 816 / 1003 and 48.6–55.7. A merge must keep or beat these. A number that went down means the
  merge changed behaviour: find the line that did it, fix or revert it, then merge again. Never ship "everything broke".
- **How to check, in order:** `python -m pytest tests/terminal -k drafting` — the six `coder-iq1_m` failures from the
  branch's own DFlash2 work may stay, nothing else; `node --test tests/drafting.test.mjs tests/split-app.test.mjs
  tests/ui-r3.test.mjs` in `apps/host` — all green; full `npm test` in `apps/host` — the four old failures
  (chat-shell #4783, model-directory, ui-do file actions, markdown-crlf) may stay, nothing new; then restart the engine,
  run `.venv\Scripts\python.exe .orca\bench-pack-ab.py strata-ud-iq1_m.json`, and send one chat call with
  `Origin: http://127.0.0.1:8081` and `"strata_mcp": true` — it must answer; an unknown origin must still get a 403.
- **The rule for the next custom change:** put every local speed or behaviour change in one place (Python's table or the
  run config), let the app read it from Control, and write it here. Never a third copy a merge can silently drop — that
  is exactly how this PC lost its speed on 2026-11-06.

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
