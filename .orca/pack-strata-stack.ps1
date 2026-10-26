Param(
    [switch]$StageOnly,
    [switch]$ArchiveOnly
)
# pack-strata-stack.ps1 - build the offline "one file" installer bundle for the new machine.
# Stage  : robocopy the runtime pieces of this machine into D:\Strata-Stage (same D:\GitHub layout)
# Archive: 7zr a -t7z -mx0 D:\Strata-Stack-Offline.7z (store mode; already-quantized weights do not compress)
$ErrorActionPreference = 'Stop'
$src       = 'D:\GitHub'
$data      = 'D:\GitHub\Strata-data'
$image     = 'D:\ai-image-spike'
$local     = "$env:LOCALAPPDATA\strata-stack"
$stage     = 'D:\Strata-Stage'
$out7z     = 'D:\Strata-Stack-Offline-20261024.7z'
$seven     = "$stage\_build\7zr.exe"

function RC($a, $b, $excludeDirs, $excludeFiles) {
    New-Item -ItemType Directory -Force $b | Out-Null
    $rob = @($a, $b, '/E', '/NFL', '/NDL', '/NJH', '/NP', '/MT:16')
    if ($excludeDirs)  { $rob += @('/XD') + $excludeDirs }
    if ($excludeFiles) { $rob += @('/XF') + $excludeFiles }
    robocopy @rob
    if ($LASTEXITCODE -ge 8) { throw "robocopy EXIT $LASTEXITCODE : $a -> $b" }
}

function File-Copy($pairs) {
    foreach ($p in $pairs) {
        $s = $p.src; $d = $p.dst
        New-Item -ItemType Directory -Force (Split-Path $d -Parent) | Out-Null
        Copy-Item $s $d -Force
    }
}

Clear-Host
Write-Host '=== pack-strata-stack ==='

# ---- STAGE ----
if (-not $ArchiveOnly) {
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    New-Item -ItemType Directory -Force $stage | Out-Null
    New-Item -ItemType Directory -Force "$stage\_build" | Out-Null

    # 1. Strata runtime (repo subset; NO logs, NO .git, NO dev trees)
    RC "$src\Strata\serve"   "$stage\Strata\serve"
    RC "$src\Strata\engine"  "$stage\Strata\engine"
    RC "$src\Strata\data"    "$stage\Strata\data"
    RC "$src\Strata\.venv"   "$stage\Strata\.venv" @('__pycache__') @('*.pyc')
    File-Copy @(
        # launcher + live configs + learned profiles + lan firewall helper
        @{src="$src\Strata\run-q2_0-v144-refusal.bat";       dst="$stage\Strata\run-q2_0-v144-refusal.bat"}
        @{src="$src\Strata\strata-q2_0-v144-refusal.json";   dst="$stage\Strata\strata-q2_0-v144-refusal.json"}
        @{src="$src\Strata\strata-ornith-ice23.json";        dst="$stage\Strata\strata-ornith-ice23.json"}
        @{src="$src\Strata\expert-profile-learned-q2_0.bin"; dst="$stage\Strata\expert-profile-learned-q2_0.bin"}
        @{src="$src\Strata\expert-profile-learned.bin";      dst="$stage\Strata\expert-profile-learned.bin"}
        @{src="$src\Strata\allow-lan-firewall.bat";          dst="$stage\Strata\allow-lan-firewall.bat"}
    )

    # 2. Strata-data: the serving model + pack + MTP + mmproj + engine binaries
    RC "$data\packs\q2_0"     "$stage\Strata-data\packs\q2_0"
    RC "$data\models\Q2_0"    "$stage\Strata-data\models\Q2_0"
    RC "$data\mtp"            "$stage\Strata-data\mtp"
    File-Copy @(
        @{src="$data\models\mmproj-Qwen3.8-Flash-Next-Uncensored-Q8_0.gguf"; dst="$stage\Strata-data\models\mmproj-Qwen3.8-Flash-Next-Uncensored-Q8_0.gguf"}
        @{src="$data\models\mmproj-Qwen3.8-Flash-Next-BF16.gguf";           dst="$stage\Strata-data\models\mmproj-Qwen3.8-Flash-Next-BF16.gguf"}
        @{src="$data\build-wc\strata.exe";     dst="$stage\Strata-data\build-wc\strata.exe"}
        @{src="$data\build-wc\strata_kq.dll";  dst="$stage\Strata-data\build-wc\strata_kq.dll"}
    )

    # 3. AI Gateway repo (its .venv included) - exclude .git
    RC "$src\AI-Gateway-MLX" "$stage\AI-Gateway-MLX" @('.git') @('*.log')

    # 4. ai-image-spike: sd runtime DLLs + the three model files (no gallery/out/zip buildkits)
    RC "$image\sd" "$stage\ai-image-spike\sd"
    File-Copy @(
        @{src="$image\flux-2-klein-4b-Q4_0.gguf";   dst="$stage\ai-image-spike\flux-2-klein-4b-Q4_0.gguf"}
        @{src="$image\flux2-klein-vae.safetensors"; dst="$stage\ai-image-spike\flux2-klein-vae.safetensors"}
        @{src="$image\Qwen3-4B-Q4_K_M.gguf";        dst="$stage\ai-image-spike\Qwen3-4B-Q4_K_M.gguf"}
    )

    # 5. bundled Python runtime (the venv points here after install.ps1 patches pyvenv.cfg)
    RC 'C:\Users\ADMIN\AppData\Local\Programs\Python\Python312' "$stage\python312"

    # 6. %LOCALAPPDATA%\strata-stack scripts (restart + stack.env template; NO logs, NO baks)
    File-Copy @(
        @{src="$local\restart-strata.ps1"; dst="$stage\strata-stack\restart-strata.ps1"}
        @{src="$local\stack.env";          dst="$stage\strata-stack\stack.env.template"}
    )

    # 7. installer + readme (identified by the write pack in this session)
    Copy-Item 'D:\GitHub\Strata\.orca\bundle-install.ps1' "$stage\install.ps1" -Force
    Copy-Item 'D:\GitHub\Strata\.orca\bundle-README.txt'  "$stage\README.txt"  -Force

    $tot = Get-ChildItem $stage -Recurse -Force -File | Measure-Object Length -Sum
    Write-Host ('STAGE done: {0} files, {1:N1} GiB' -f $tot.Count, ($tot.Sum/1GB))
}

# ---- ARCHIVE ----
if (-not $StageOnly) {
    if (-not (Test-Path $seven)) {
        Write-Host 'downloading standalone 7zr.exe (7-zip.org)...'
        New-Item -ItemType Directory -Force (Split-Path $seven -Parent) | Out-Null
        Invoke-WebRequest 'https://www.7-zip.org/a/7zr.exe' -OutFile $seven -UseBasicParsing
    }
    if (Test-Path $out7z)        { Remove-Item $out7z -Force }
    Push-Location $stage
    & $seven a -t7z -mx0 -x!_build $out7z '.\*' | Out-Null
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -ne 0) { throw "7z EXIT $code" }
    $sz = (Get-Item $out7z).Length / 1GB
    Write-Host ('ARCHIVE done: {0}  ({1:N2} GiB)' -f $out7z, $sz)
}
Write-Host '=== pack done ==='
