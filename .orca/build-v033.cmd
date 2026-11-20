@echo off
rem Build the merged v0.2.16 source (engine 0.1.62, own-stack) into build-v033.
rem Source moved to engine\ in 0.2.16; llama.cpp's MMQ options are gone, the ggml is the
rem vendored engine\third_party\strata-ggml (no -DSTRATA_GGML_DIR). Does not touch
rem build-v032 or the running serve.
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 (echo vcvars FAIL & exit /b 1)
D:\GitHub\Strata\.venv\Scripts\cmake.exe -S D:\GitHub\Strata\engine -B D:\GitHub\Strata-data\build-v033 -G Ninja ^
  -DCMAKE_MAKE_PROGRAM=D:\GitHub\Strata\.venv\Scripts\ninja.exe ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_CUDA_ARCHITECTURES=86 ^
  -DSTRATA_ENABLE_CUDA=ON -DSTRATA_ENABLE_HIP=OFF -DSTRATA_ENABLE_SYCL=OFF ^
  -DSTRATA_BUILD_TESTS=OFF -DSTRATA_BUILD_CONVERSATION_TESTS=OFF ^
  -DSTRATA_NATIVE_EXPERTS=ON -DSTRATA_Q6K_EXPERTS=ON ^
  -DSTRATA_PORTABLE=ON -DSTRATA_WERROR=OFF ^
  -DBUILD_SHARED_LIBS=OFF
if errorlevel 1 (echo CONFIGURE FAIL & exit /b 1)
echo === configure OK, build starts ===
D:\GitHub\Strata\.venv\Scripts\cmake.exe --build D:\GitHub\Strata-data\build-v033 --target strata -j 6
if errorlevel 1 (echo BUILD FAIL & exit /b 1)
echo === BUILD OK ===
D:\GitHub\Strata-data\build-v033\strata.exe --version
dir /b D:\GitHub\Strata-data\build-v033\strata.exe
