@echo off
setlocal
cd /d "%~dp0"

set "EXE="
for %%P in (
  "build\bin\NetworkMonitorCpp.exe"
  "build\bin\Release\NetworkMonitorCpp.exe"
  "build\bin\Debug\NetworkMonitorCpp.exe"
  "build\Release\NetworkMonitorCpp.exe"
  "build\Debug\NetworkMonitorCpp.exe"
) do (
  if exist %%~P (
    set "EXE=%%~P"
    goto :found
  )
)

echo [info] Executavel C++ nao encontrado. Compilando...
cmake -S . -B build
if errorlevel 1 (
  echo [erro] cmake configure falhou.
  exit /b 1
)
cmake --build build --config Release
if errorlevel 1 (
  echo [erro] cmake build falhou.
  exit /b 1
)

for %%P in (
  "build\bin\NetworkMonitorCpp.exe"
  "build\bin\Release\NetworkMonitorCpp.exe"
  "build\bin\Debug\NetworkMonitorCpp.exe"
  "build\Release\NetworkMonitorCpp.exe"
  "build\Debug\NetworkMonitorCpp.exe"
) do (
  if exist %%~P (
    set "EXE=%%~P"
    goto :found
  )
)

echo [erro] Build concluiu, mas NetworkMonitorCpp.exe nao foi encontrado.
exit /b 1

:found
"%EXE%" %*
exit /b %ERRORLEVEL%
