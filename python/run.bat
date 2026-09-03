@echo off
setlocal
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" main.py %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 main.py %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python main.py %*
  exit /b %ERRORLEVEL%
)

echo [erro] Python nao encontrado. Crie um venv em python\venv ou instale Python 3.10+.
exit /b 1
