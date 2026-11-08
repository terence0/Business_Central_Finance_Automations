@echo off
setlocal

rem Yooz Routing Automation (Vendor H) - runs in this console window.
rem
rem Builds the Yooz cost centre routing import from "Vendor & Cost Centre
rem Routing.xlsx" and emails it through the local Outlook desktop app, so
rem Outlook must be installed and signed in.
rem
rem Runs the maintained copy in "Automations", brought up to date with
rem the older shared copy on 19 Oct 2026 (including the entity-specific cost centre
rem overrides). It does not use Business Central, so it has no sandbox version.

call "%~dp0..\_find_project.cmd" "Finance Systems\Automations\approval-routing" "routingScript.py" || (pause & exit /b 1)

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

call "%~dp0..\_ensure_venv.cmd" "yooz_routing_automation" "%PROJECT_DIR%\requirements.txt" || (pause & exit /b 1)

cd /d "%PROJECT_DIR%"
"%VENV_PY%" routingScript.py
pause
