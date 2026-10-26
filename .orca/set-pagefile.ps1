# Tao pagefile D:\pagefile.sys 96 GiB (98304 MB) - can chay voi quyen admin (UAC)
try {
  Set-WmiInstance -Class Win32_PageFileSetting -Arguments @{ Name = 'D:\pagefile.sys'; InitialSize = 98304; MaximumSize = 98304 } | Out-Null
  'Set-WmiInstance OK' | Out-File D:\GitHub\Strata\.orca\pagefile-set.err.txt -Encoding utf8
} catch {
  $_.Exception.Message | Out-File D:\GitHub\Strata\.orca\pagefile-set.err.txt -Encoding utf8
}
Get-CimInstance Win32_PageFileSetting | Format-Table Name, InitialSize, MaximumSize -AutoSize |
  Out-File D:\GitHub\Strata\.orca\pagefile-set.log -Encoding utf8
