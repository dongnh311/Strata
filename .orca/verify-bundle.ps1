& 'D:\GitHub\Strata\.orca\pack-strata-stack.ps1' -ArchiveOnly
if ($LASTEXITCODE) { throw 'archive step failed' }
'testing archive...'
$z = 'D:\Strata-Stage\_build\7zr.exe'
& $z t D:\Strata-Stack-Offline-20261024.7z | Select-Object -Last 4
$h = Get-FileHash D:\Strata-Stack-Offline-20261024.7z -Algorithm SHA256
'SHA256 ' + $h.Hash
'{0:N2} GiB  {1:N0} bytes' -f ((Get-Item D:\Strata-Stack-Offline-20261024.7z).Length/1GB), (Get-Item D:\Strata-Stack-Offline-20261024.7z).Length
