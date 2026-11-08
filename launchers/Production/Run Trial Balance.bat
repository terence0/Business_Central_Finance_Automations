@echo off
setlocal

rem Trial Balance - opens in your browser.
rem
rem Trial Balance extract to Excel. Read only. Used to point at the
rem "older shared" copy, which has since been restructured.
rem
rem Runs from the maintained copy of the Query tool. Environment setup is left
rem to that project's own _launch.bat (private venv, reinstall when
rem requirements.txt changes); path resolution is the shared include's job.
rem
rem Production / Sandbox: this file runs against Production. Its twin
rem "..\Sandbox\Run Trial Balance (Sandbox).bat" runs the same automation against the Business Central
rem sandbox named in _bc_environment.cmd, on port +100, so both can be open
rem at once. Nothing needs editing to switch.

call "%~dp0..\_bc_environment.cmd" "%~1"

call "%~dp0..\_find_project.cmd" "Finance Systems\Automations\bc-query-tool" "trialBalance.py" || (pause & exit /b 1)

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

call "%PROJECT_DIR%\_launch.bat" trialBalance.py 8503 "Trial Balance Query"
exit /b %ERRORLEVEL%
