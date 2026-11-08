@echo off
setlocal

rem Fiscal Year Close - opens in your browser.
rem
rem Manages the Fiscal Year Close Automation extension in every company:
rem setup, closing journal, full close, log. Reads its sign-in from the .env
rem file in the streamlit_app folder. The environment chosen here is where it
rem opens; Production stays locked until unlocked in the sidebar, and still
rem needs ALLOW_PRODUCTION_UPDATES=true in .env.
rem
rem Production / Sandbox: this file runs against Production. Its twin
rem "..\Sandbox\Run Fiscal Year Close Automation (Sandbox).bat" runs the same automation against the Business Central
rem sandbox named in _bc_environment.cmd, on port +100, so both can be open
rem at once. Nothing needs editing to switch.

call "%~dp0..\_bc_environment.cmd" "%~1"

call "%~dp0..\_find_project.cmd" "Finance Systems\Automations\fiscal-year-close\streamlit_app" "streamlit_app.py" || (pause & exit /b 1)

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

call "%~dp0..\_ensure_venv.cmd" "fiscal_year_close_automation" "%PROJECT_DIR%\requirements.txt" || (pause & exit /b 1)

set /a APP_PORT=8510+%BC_PORT_OFFSET%
title Fiscal Year Close - %BC_ENVIRONMENT_NAME%
echo   Opening at http://localhost:%APP_PORT%
cd /d "%PROJECT_DIR%"
"%VENV_PY%" -m streamlit run streamlit_app.py --server.port %APP_PORT% --browser.gatherUsageStats false
pause
