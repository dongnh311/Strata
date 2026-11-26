# Restart the Inkling server through the router and wait until it serves again.
$ErrorActionPreference = "Stop"
$cfg = Get-Content D:\GitHub\Strata\terminal\strata-ud-q2_0-tuned.json -Raw | ConvertFrom-Json
$key = $cfg.api_key
$hdr = @{ Authorization = "Bearer $key" }
$body = '{"model":"inkling-2-mini-sq-10","restart":true}'
Invoke-WebRequest "http://127.0.0.1:8081/v1/load" -Method Post -Headers $hdr -ContentType 'application/json' -Body $body -TimeoutSec 60 -UseBasicParsing | Out-Null
$deadline = (Get-Date).AddSeconds(300)
$h = $null
while ((Get-Date) -lt $deadline) {
    Start-Sleep 5
    try { $h = Invoke-RestMethod http://127.0.0.1:8000/health -Headers $hdr -TimeoutSec 5 } catch { $h = $null }
    if ($h -and $h.loaded) { break }
}
if (-not $h -or -not $h.loaded) { "NOT READY"; exit 1 }
"ready: model=$($h.model) ctx=$($h.max_context) images=$($h.images)"
