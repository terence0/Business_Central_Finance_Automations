@echo off
setlocal

rem Query tool - General Ledger query, prompt-driven in this console window.
rem
rem Runs query.py from the maintained copy of the Query tool. It used to point
rem at the "older shared" copy, which has since been restructured.
rem
rem Production / Sandbox: this file runs against Production. Its twin
rem "..\Sandbox\Run Query Tool (Sandbox).bat" runs the same automation against the Business Central
rem sandbox named in _bc_environment.cmd, on port +100, so both can be open
rem at once. Nothing needs editing to switch.

call "%~dp0..\_bc_environment.cmd" "%~1"

call "%~dp0..\_find_project.cmd" "Finance Systems\Automations\bc-query-tool" "query.py" || (pause & exit /b 1)

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

cd /d "%PROJECT_DIR%"
call "%PROJECT_DIR%\_venv_setup.bat" || (pause & exit /b 1)
"%QT_PY%" query.py
pause
