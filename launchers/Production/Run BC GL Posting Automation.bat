@echo off
setlocal

rem BC GL Posting Automation - opens in your browser.
rem
rem Updates General Ledger Setup > Allow Posting From across entities. Writes
rem to Business Central; Production is refused unless ALLOW_PRODUCTION_UPDATES=true
rem in its .env.
rem
rem Production / Sandbox: this file runs against Production. Its twin
rem "..\Sandbox\Run BC GL Posting Automation (Sandbox).bat" runs the same automation against the Business Central
rem sandbox named in _bc_environment.cmd, on port +100, so both can be open
rem at once. Nothing needs editing to switch.

call "%~dp0..\_bc_environment.cmd" "%~1"

call "%~dp0..\_find_project.cmd" "Finance Systems\Automations\gl-posting-automation" "app.py" || (pause & exit /b 1)

where python >nul 2>nul
if errorlevel 1 (
    py -3 -c "import sys" >nul 2>nul
    if errorlevel 1 (
        echo.
        echo   Python was not found on this computer.
        echo   Install Python 3.11 or later from the Company Portal or
        echo   https://python.org ^(tick "Add python.exe to PATH"^), then
        echo   run this again.
        echo.
        pause
        exit /b 1
    )
)

call "%~dp0..\_ensure_venv.cmd" "bc_gl_posting_automation" "%PROJECT_DIR%\requirements.txt" || (pause & exit /b 1)

set /a APP_PORT=8512+%BC_PORT_OFFSET%
title BC GL Posting Automation - %BC_ENVIRONMENT_NAME%
echo   Opening at http://localhost:%APP_PORT%
cd /d "%PROJECT_DIR%"
"%VENV_PY%" -m streamlit run app.py --server.port %APP_PORT% --browser.gatherUsageStats false
pause
