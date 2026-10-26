param(
  [Parameter(Mandatory=$true)][string]$Repo,
  [Parameter(Mandatory=$true)][string]$Gf,
  [Parameter(Mandatory=$true)][long]$Total,
  [Parameter(Mandatory=$true)][int]$Parts,
  [Parameter(Mandatory=$true)][string]$Outdir,
  [Parameter(Mandatory=$true)][string]$Log
)
# Tai 1 file tu HF bang nhieu phan curl -r song song, moi phan CHI 1 curl tai mot thoi diem
# (khong spawn trung: truoc khi spawn kiem tra process curl con song cho phan do), moi phan resumable.
# Ghep o cuoi; xoa part ngay sau khi ghep.
$ErrorActionPreference = 'Continue'
$url = "https://huggingface.co/$Repo/resolve/main/$Gf"
$work = Join-Path $Outdir (Join-Path '_parts' $Gf)
New-Item -ItemType Directory -Force -Path $work | Out-Null
$workEsc = [regex]::Escape($work)

$base = [math]::Ceiling($Total / $Parts)
$expect = New-Object 'long[]' $Parts
for ($i = 0; $i -lt $Parts; $i++) {
  $s = [long]$i * $base
  $e = [Math]::Min($Total, $s + $base) - 1
  if ($e -lt $s) { $e = $Total - 1 }
  $expect[$i] = $e - $s + 1
}
function PartSize([int]$j) {
  $p = Join-Path $work ("part_{0:d3}" -f $j)
  if (Test-Path -LiteralPath $p) { (Get-Item -LiteralPath $p -Force).Length } else { 0 }
}
function AppendLog([string]$msg) { Add-Content -Path $Log -Value $msg }
AppendLog ("START {0} : {1:N0} bytes, {2} parts" -f $Gf, $Total, $Parts)

$sw = [Diagnostics.Stopwatch]::StartNew()
$lastDone = [long]0
$round = 0
$ok = $false
while ($round -lt 3000) {
  $round++
  $alive = @{}
  Get-CimInstance Win32_Process -Filter "Name='curl.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
    $cl = $_.CommandLine
    if ($cl -and $cl -match [regex]::Escape($workEsc) -and $cl -match 'part_(\d{3})') { $alive[[int]$Matches[1]] = $true }
  }
  $pending = @()
  for ($i = 0; $i -lt $Parts; $i++) {
    if ((PartSize $i) -ne $expect[$i]) { $pending += $i }
  }
  if ($pending.Count -eq 0) { $ok = $true; break }
  foreach ($i in $pending) {
    if ($alive.ContainsKey($i)) { continue }
    $p = Join-Path $work ("part_{0:d3}" -f $i)
    $have = PartSize $i
    $s = [long]$i * $base + $have
    $e = [Math]::Min($Total, ([long]($i) + 1) * $base) - 1
    if ($s -gt $e) { continue }
    $rel = "$s-$e"
    $cline = "-sS -L --fail --connect-timeout 20 --speed-limit 20480 --speed-time 45 -H `"User-Agent: strata-curl/1.0`" -r $rel -a -o $p $url"
    Start-Process -FilePath 'curl.exe' -ArgumentList $cline -WindowStyle Hidden -RedirectStandardError (Join-Path $work ("curl_{0:d3}.err" -f $i)) | Out-Null
  }
  Start-Sleep -Seconds 10
  $done = [long]0
  for ($i = 0; $i -lt $Parts; $i++) { $done += (PartSize $i) }
  $rate = ($done - $lastDone) / 10.0 / 1MB
  $lastDone = $done
  AppendLog ("ROUND {0}: {1:F2} / {2:F2} GB : {3:F1} MB/s : curl_song_song {4}: pending {5}" -f $round, ($done / 1GB), ($Total / 1GB), $rate, $alive.Count, (($pending | Select-Object -First 12) -join ','))
}
if (-not $ok) { AppendLog "FAIL sau $round dong; cho con: $($pending -join ',')"; exit 1 }

$final = Join-Path $Outdir $Gf
$fsOut = [System.IO.File]::Open($final, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
for ($i = 0; $i -lt $Parts; $i++) {
  $p = Join-Path $work ("part_{0:d3}" -f $i)
  $fsIn = [System.IO.File]::OpenRead($p)
  $fsIn.CopyTo($fsOut, 33554432)
  $fsIn.Dispose()
  $fsOut.Flush()
  Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath (Join-Path $work ("curl_{0:d3}.err" -f $i)) -Force -ErrorAction SilentlyContinue
}
$fsOut.Dispose()
$len = (Get-Item -LiteralPath $final -Force).Length
AppendLog ("ALL DONE {0}: {1:N0} bytes (ky vong {2:N0}) : {3:F0} s" -f $Gf, $len, $Total, $sw.Elapsed.TotalSeconds)
if ($len -ne $Total) { AppendLog "CANH BAO: kich thuoc khac ky vong!"; exit 2 }
