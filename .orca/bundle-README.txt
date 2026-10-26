STRATA STACK - OFFLINE BUNDLE (RTX 3060 12 GB + 48 GiB RAM)

What this is: one .7z that carries the complete working setup from the donor
machine - Strata engine + server + Qwen3.8-Flash-Next q2_0 (61.9 GiB, 2 shards),
MTP draft pack, vision mmproj, AI Gateway (:8090), image sidecar (:8096 with
FLUX Klein + Qwen3-4B), bundled Python 3.12 runtime, scheduled tasks and the
live serve config. No internet is needed on the target machine.

HOW TO INSTALL (about 15 minutes after extraction)
1. Plug the drive with this .7z into the new machine.
2. Install 7-Zip if the machine does not have it (https://www.7-zip.org).
3. Extract the archive STRAIGHT INTO D:\GitHub (right-click the .7z in the
   drive -> 7-Zip -> Extract files... -> D:\GitHub). The configs use absolute
   D:\GitHub\... paths, so a different folder means editing them by hand.
   D:\GitHub can exist already; it must only have >= 90 GiB free.
4. Open PowerShell AS ADMINISTRATOR and run:
       powershell -ExecutionPolicy Bypass -File D:\GitHub\install.ps1
   The script then does the rest by itself: patches the venvs to the bundled
   Python, installs %LOCALAPPDATA%\strata-stack scripts, checks/sets the
   pagefile (use the -SetPagefile switch when asked), opens the LAN firewall,
   registers the StrataStack + StrataRestart tasks, boots the whole stack and
   runs a smoke prompt against :18080. Everything it does is logged to
   %LOCALAPPDATA%\strata-stack\install.log.
5. If it asked for a pagefile change: reboot once, re-run install.ps1.

AFTER INSTALL - WHAT ANSWERS WHERE
  Chat/API (OpenAI-compatible) : http://127.0.0.1:18080/v1  (key in
      D:\GitHub\Strata\strata-q2_0-v144-refusal.json -> api_key)
  AI Gateway (tools/bridge)    : http://127.0.0.1:8090
  Image sidecar (gallery)      : http://127.0.0.1:8096
  Logs of every boot           : %LOCALAPPDATA%\strata-stack\start-all.log,
                                 and the serve log next to the .bat in Strata\

MANUAL BITS (not automated, by design)
- Tailscale: log in on the new machine, then re-run the two forwards:
      tailscale serve --bg --https=8443 http://127.0.0.1:18080
      tailscale serve --bg --https=8444 http://127.0.0.1:8096
  IMAGE_PUBLIC_BASE was dropped from stack.env on purpose - start-all.ps1
  picks up whatever `tailscale serve` is active on the new machine.
- If you expose the API beyond 127.0.0.1, check "allowed_hosts" inside
  strata-q2_0-v144-refusal.json; it still carries the donor machine's
  tailnet names and should be replaced with the new machine's.

TO SAFELY STOP / RESTART THE STACK
  Restart everything:  powershell -File %LOCALAPPDATA%\strata-stack\restart-strata.ps1
  Stop the serve:      D:\GitHub\Strata\strata-launch --stop (or close the
                       cmd windows; the stack restarts at next logon).
  The StrataStack task fires ~30 s after logon; nothing is auto-started at
  boot before you log in.

WHAT IS INSIDE THE ARCHIVE
  Strata\            engine (build 0.1.47 windows-coding), serve\, data\,
                     .venv (722 MB incl. CUDA 13 runtime DLLs), live bat/config
  Strata-data\       model shards 1-2 (q2_0), pack q2_0, MTP pack (mtp\ incl.
                     rt\), both mmproj GGUFs, engine strata.exe + strata_kq.dll
  AI-Gateway-MLX\    gateway repo incl. its scripts + venv
  ai-image-spike\    sd-cli + CUDA 12 DLLs + FLUX Klein 4B + VAE + Qwen3-4B
  python312\         bundled CPython 3.12 runtime (venvs point here)
  strata-stack\      restart-strata.ps1 + stack.env template
  install.ps1        the installer (step 4 above)

Total content ≈ 74 GiB. The archive is stored (not recompressed) because
quantized weights do not compress; copying it is IO-speed bound.
