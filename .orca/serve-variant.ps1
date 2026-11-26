# Start a variant serve on a test port and wait until the model is loaded.
param(
    [string]$Cfg = "terminal\strata-ud-q2_0-tuned.json",
    [int]$Port = 18082,
    [string]$Log = "$env:TEMP\opencode\variant-serve.log"
)
$ErrorActionPreference = "Stop"
$root = "D:\GitHub\Strata"
$p = (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
if ($p) { taskkill /PID $p /T /F 2>$null | Out-Null; Start-Sleep 4 }
$exe = Join-Path $root ".venv\Scripts\python.exe"
Start-Process -FilePath $exe `
    -ArgumentList @("terminal\serve\server.py", "--engine", "strata", "--config", $Cfg, "--port", $Port) `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput ($Log + ".out") -RedirectStandardError ($Log + ".err") | Out-Null
$cfg = Get-Content (Join-Path $root $Cfg) -Raw | ConvertFrom-Json
$hdr = @{ Authorization = "Bearer $($cfg.api_key)" }
$deadline = (Get-Date).AddMinutes(10)
$h = $null
while ((Get-Date) -lt $deadline) {
    Start-Sleep 8
    try { $h = Invoke-RestMethod "http://127.0.0.1:$Port/health" -Headers $hdr -TimeoutSec 5 } catch { $h = $null }
    if ($h -and $h.loaded) { break }
}
if ($h -and $h.loaded) {
    "ready port=$Port model=$($h.model) ctx=$($h.max_context) images=$($h.images)"
} else {
    "NOT READY"
    Get-Content ($Log + ".out") -Tail 12 -ErrorAction SilentlyContinue
    Get-Content ($Log + ".err") -Tail 12 -ErrorAction SilentlyContinue
    exit 1
}
