& 'D:\Strata-Stage\_build\7zr.exe' t D:\Strata-Stack-Offline-20261024.7z | Select-String -Pattern 'Everything|^ERROR'
'exit ' + $LASTEXITCODE
