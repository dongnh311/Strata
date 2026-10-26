Param(
    [switch]$Check,
    [switch]$SkipTasks,
    [switch]$SetPagefile
)
# install.ps1 - finalize the Strata stack after extracting this bundle to D:\GitHub.
# Run from an Administrator PowerShell:  powershell -ExecutionPolicy Bypass -File D:\GitHub\install.ps1
# Steps (each resumable by re-running): preflight -> patch venvs -> stack scripts -> pagefile
#   -> firewall -> scheduled tasks -> first boot -> health verify.
# Written for the exact hardware the bundle targets: RTX 3060 12 GB + 48 GiB RAM + NVMe D:.
$ErrorActionPreference = 'Continue'
$root      = Split-Path $PSScriptRoot -Parent            # install.ps1 sits at the extracted bundle root
$strata    = Join-Path $root 'Strata'
$gateway   = Join-Path $root 'AI-Gateway-MLX'
$stackDir  = "$env:LOCALAPPDATA\strata-stack"
$log       = Join-Path $stackDir 'install.log'
New-Item -ItemType Directory -Force $stackDir | Out-Null

function Log($m) { $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $m; Add-Content $log $line; Write-Host $line }
Log "=== install began ==="

# ---- 1. preflight -------------------------------------------------------------
if ($root -ne 'D:\GitHub') {
    Log "FATAL: extracted to '$root'. The bundle's absolute configs require D:\GitHub. Extract the .7z straight into D:\GitHub and re-run."; exit 1
}
foreach ($p in @("$strata\serve\server.py", "$root\Strata-data\models\Q2_0\Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00001-of-00002.gguf", "$strata\.venv\Scripts\python.exe", "$root\python312\python.exe", "$gateway\serve" -replace 'serve$','scripts\windows\start-all.ps1', "$root\ai-image-spike\sd\sd-cli.exe")) {
    if (-not (Test-Path $p)) { Log "FATAL: missing $p"; exit 1 }
}
$free = (Get-PSDrive D).Free / 1GB
if ($free -lt 5) { Log ("FATAL: D: has only {0:N1} GiB free" -f $free); exit 1 }
$gpu = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' } | Select-Object -First 1
if (-not $gpu -or $gpu.AdapterRAM -lt 10GB -and -not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { Log "WARNING: no NVIDIA high-VRAM GPU detected - model will not boot" }
$ram = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB
if ($ram -lt 40) { Log ("WARNING: RAM {0:N1} GiB (bundle tuned for 48 GiB)" -f $ram) }
& nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>$null | ForEach-Object { Log "GPU: $_" }
Log ("preflight ok: D: free {0:N0} GiB, RAM {1:N1} GiB" -f $free, $ram)

# ---- 2. patch the venvs to the bundled Python ---------------------------------
foreach ($cfgpath in @("$strata\.venv\pyvenv.cfg", "$gateway\.venv\pyvenv.cfg")) {
    if (Test-Path $cfgpath) {
        $c = Get-Content $cfgpath
        $c = $c | ForEach-Object { $_ -replace '^home\s*=.*', "home = $root\python312" -replace '^executable\s*=.*', "executable = $root\python312\python.exe" }
        Set-Content $cfgpath $c
        Log "patched $cfgpath -> bundled python"
    }
}
& "$strata\.venv\Scripts\python.exe" -c "import sys; print('python ok', sys.version.split()[0])" | ForEach-Object { Log $_ }

# ---- 3. stack scripts (%LOCALAPPDATA%\strata-stack) ----------------------------
Copy-Item "$PSScriptRoot\strata-stack\restart-strata.ps1" "$stackDir\restart-strata.ps1" -Force
# stack.env: keep the launcher/config lines from the template, drop the old machine's tailscale base
# (start-all.ps1 auto-detects `tailscale serve` at run time; add IMAGE_PUBLIC_BASE back by hand if wanted)
$envlines = Get-Content "$PSScriptRoot\strata-stack\stack.env.template" | Where-Object { $_ -notmatch '^IMAGE_PUBLIC_BASE' -and $_ -notmatch '^#' }
Set-Content "$stackDir\stack.env" $envlines
Log "stack scripts installed"

# ---- 4. pagefile (the model + expert pinning need a large commit limit) --------
$os = Get-CimInstance Win32_OperatingSystem
$commitLimit = ($os.TotalVirtualMemorySize / 1MB)   # KiB -> GiB
if ($commitLimit -lt 150) {
    Log ("commit limit {0:N1} GiB is below the ~150 GiB the 61.9 GiB model + pinned experts need. " -f $commitLimit)
    if ($SetPagefile) {
        $uac = Join-Path $stackDir '_setpagefile.ps1'
        Set-Content $uac @'
$t = Get-CimInstance Win32_PageFileSetting -Filter "Name='D:\pagefile.sys'" -ErrorAction SilentlyContinue
if ($t) { $t | Set-CimInstance -Property @{InitialSize=[uint32]98304; MaximumSize=[uint32]98304} } else { Set-WmiInstance -Class Win32_PageFileSetting -Arguments @{Name='D:\pagefile.sys'; InitialSize=[uint32]98304; MaximumSize=[uint32]98304} | Out-Null }
'@
        Start-Process powershell -Verb RunAs -Wait -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File', $uac)
        Log "pagefile VOLLUM 96 GiB requested on D: (Set in elevated shell). REBOOT the machine once, then re-run: powershell -ExecutionPolicy Bypass -File $PSScriptRoot\install.ps1"
    } else {
        Log "run again with -SetPagefile (UAC dialog will show) or set a 96 GiB pagefile on D: by hand, then reboot."
    }
} else { Log ("commit limit ok: {0:N1} GiB" -f $commitLimit) }

# ---- 5. firewall (LAN exposure, config serves on 0.0.0.0) ----------------------
if (Test-Path "$strata\allow-lan-firewall.bat") {
    Start-Process cmd -Verb RunAs -Wait -ArgumentList '/c', "`"$strata\allow-lan-firewall.bat`""
    Log "firewall batch ran (elevated)"
}

# ---- 6. scheduled tasks (StrataStack = project bootstrapper) -------------------
if (-not $SkipTasks) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$gateway\scripts\windows\install-autostart.ps1"
    Log "StrataStack task registered via install-autostart.ps1"
    $uac2 = Join-Path $stackDir '_regrestart.ps1'
    Set-Content $uac2 @'
$name = "StrataRestart"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$env:LOCALAPPDATA\strata-stack\restart-strata.ps1`"")
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries) -Force | Out-Null
'@
    Start-Process powershell -Verb RunAs -Wait -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File', $uac2)
    Log "StrataRestart task registered (highest run level)"
}

# ---- 7. first boot -------------------------------------------------------------
if (-not $Check) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$gateway\scripts\windows\start-all.ps1"
    # ---- 8. verify -------------------------------------------------------------
    try {
        $cfg = Get-Content "$strata\strata-q2_0-v144-refusal.json" -Raw | ConvertFrom-Json
        $h = @{Authorization = "Bearer $($cfg.api_key)"}
        $st = Invoke-RestMethod http://127.0.0.1:18080/health -Headers $h -TimeoutSec 10
        Log ("health=" + $st.status + " loaded=" + $st.loaded + " model=" + $st.model)
        $mcp = Invoke-RestMethod http://127.0.0.1:18080/mcp -Headers $h -TimeoutSec 10
        Log ("tool servers: " + (($mcp.servers | ForEach-Object { "$($_.name)=$($_.status)" }) -join ', '))
        $b = @{model=$cfg.model_name; max_tokens=8; messages=@(@{role='user'; content='Reply with exactly: OK'})} | ConvertTo-Json -Depth 4
        $s = Invoke-RestMethod 'http://127.0.0.1:18080/v1/chat/completions' -Method Post -Headers $h -Body ([System.Text.Encoding]::UTF8.GetBytes($b)) -TimeoutSec 120 -ContentType 'application/json'
        Log ("smoke reply: " + (($s.choices[0].message.content -replace '\s+',' ').Trim()))
    } catch { Log "verify failed: $($_.Exception.Message)" }
}

Log '=== install done. If any step failed above, fix and re-run: powershell -ExecutionPolicy Bypass -File install.ps1 ==='
Log 'Tailscale (optional): re-run `tailscale serve` for 8443->18080 and 8444->8096, then add allowed_hosts in config if needed.'
Log 'Delete install.ps1 / README.txt / strata-stack\\ / python312 leftovers from D:\GitHub whenever you like.'
exit 0
