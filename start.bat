@echo off
setlocal

echo.
echo  ============================================
echo   OBSCURA -- Start
echo  ============================================
echo.

set VENV=%~dp0.venv

if not exist "%VENV%\Scripts\python.exe" (
    echo  [ERR] Virtual environment not found.
    echo        Run install.bat first.
    pause
    exit /b 1
)

:: Read saved domain from ~/.pii_shield/config.json (falls back to "general")
for /f "delims=" %%D in ('"%VENV%\Scripts\python.exe" -c "import json,pathlib; f=pathlib.Path.home()/'.pii_shield'/'config.json'; d=json.loads(f.read_text()) if f.exists() else {}; print(d.get('default_domain','general'))" 2^>nul') do set DOMAIN=%%D
if "%DOMAIN%"=="" set DOMAIN=general

set HOST=127.0.0.1
set PORT=8080

echo  Starting OBSCURA REST API...
echo  Host   : %HOST%
echo  Port   : %PORT%
echo  Domain : %DOMAIN%
echo.
echo  API docs : http://%HOST%:%PORT%/docs
echo  Status   : http://%HOST%:%PORT%/status
echo.
echo  Press Ctrl+C to stop the server.
echo.

"%VENV%\Scripts\python.exe" "%~dp0api_server.py" --host %HOST% --port %PORT% --domain %DOMAIN% %*

if errorlevel 1 (
    echo.
    echo  [ERR] Server exited with an error. See output above.
    pause
)
