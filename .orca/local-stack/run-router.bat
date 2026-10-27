@echo off
rem Launcher for the model router (one endpoint, two local models, one loaded at a time).
rem Started by AI-Gateway-MLX\scripts\windows\start-all.ps1 at logon via stack.env STRATA_BAT.
title Strata model router (8081)
cd /d "D:\GitHub\Strata"
set MODEL_ROUTER_PORT=8081
set STRATA_PREFILL_CPU_SHARE=0
"C:\Users\ADMIN\AppData\Local\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\strata-stack\model-router.py" >> "%LOCALAPPDATA%\strata-stack\model-router-stdout.log" 2>&1