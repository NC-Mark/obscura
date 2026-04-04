@echo off
setlocal

echo.
echo  ============================================
echo   OBSCURA -- Install
echo  ============================================
echo.

:: Check py is available
where py >nul 2>&1
if errorlevel 1 (
    echo  [ERR] Python launcher ^(py^) not found.
    echo        Install Python 3.10+ from https://python.org and try again.
    pause
    exit /b 1
)

:: Get the actual Python executable path (avoids Windows Store launcher confusion)
for /f "delims=" %%P in ('py -c "import sys; print(sys.executable)"') do set PYEXE=%%P
if "%PYEXE%"=="" (
    echo  [ERR] Could not resolve Python executable path.
    pause
    exit /b 1
)

echo  Python: %PYEXE%
echo.

:: ── Create virtual environment if it doesn't exist ───────────────────────────
set VENV=%~dp0.venv

if exist "%VENV%\Scripts\python.exe" (
    echo  [OK]  Virtual environment already exists at .venv
) else (
    echo  >> Creating virtual environment at .venv ...
    "%PYEXE%" -m venv "%VENV%"
    if errorlevel 1 (
        echo  [ERR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK]  Virtual environment created.
)

echo.

:: ── Run setup.py inside the venv ─────────────────────────────────────────────
"%VENV%\Scripts\python.exe" "%~dp0setup.py" %*

if errorlevel 1 (
    echo.
    echo  [ERR] Setup failed. See errors above.
    pause
    exit /b 1
)

echo.
echo  Install complete. Run start.bat to launch the server.
echo.
pause
