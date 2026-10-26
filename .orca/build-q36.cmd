@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
"D:\GitHub\Strata\.venv\Scripts\cmake.exe" --build "D:\GitHub\Strata-data\build-wc" --target native_expert_parity iq_parity strata-q36 -j 6
