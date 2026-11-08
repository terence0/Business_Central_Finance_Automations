@echo off
setlocal

rem Chart of Accounts - opens in your browser.
rem
rem Creates a G/L account identically in every selected entity, from one form
rem or an Excel upload. WRITES to Business Central, only after a dry run has
rem been reviewed and approved on the page; an existing account is never
rem changed. Every write is logged, with its environment, to
rem logging\coa_changes.csv in the Query tool folder.
rem
rem Runs from the maintained copy of the Query tool. Environment setup is left
rem to that project's own _launch.bat (private venv, reinstall when
rem requirements.txt changes); path resolution is the shared include's job.
rem
rem Production / Sandbox: this file runs against Production. Its twin
rem "..\Sandbox\Run Chart of Accounts (Sandbox).bat" runs the same automation against the Business Central
rem sandbox named in _bc_environment.cmd, on port +100, so both can be open
rem at once. Nothing needs editing to switch.

call "%~dp0..\_bc_environment.cmd" "%~1"

call "%~dp0..\_find_project.cmd" "Finance Systems\Automations\bc-query-tool" "coaSetup.py" || (pause & exit /b 1)

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

call "%PROJECT_DIR%\_launch.bat" coaSetup.py 8506 "Chart of Accounts"
exit /b %ERRORLEVEL%
