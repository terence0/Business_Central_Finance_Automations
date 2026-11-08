@echo off
REM ===========================================================================
REM  _venv_setup.bat        Finance Query Tool
REM
REM  Shared environment bootstrap. Called by _launch.bat. Not run directly.
REM
REM  Background: the "venv" and ".venv" folders sitting in this directory are
REM  left over from individual machines. A Python venv is NOT portable: its
REM  activate.bat hardcodes the absolute path of the machine that created it
REM  (C:\Users\<that person>\OneDrive - Contoso\...), so on anyone else's
REM  PC activation appears to succeed, PATH gains a folder that does not exist,
REM  and streamlit is never found. That is exit code 9009.
REM
REM  This script therefore ignores both of them. Every user gets their own
REM  environment under %LOCALAPPDATA%, outside OneDrive, built on first run and
REM  reused afterwards. Nothing is synced, nothing is shared, nothing breaks
REM  anyone else. The folders already in this directory are left untouched.
REM
REM  On success: sets QT_PY to the python.exe to use, and exits 0.
REM ===========================================================================

set "VENV_ROOT=%LOCALAPPDATA%\FinanceQueryTool\venv"
set "QT_PY=%VENV_ROOT%\Scripts\python.exe"
set "REQ_FILE=%~dp0requirements.txt"
set "STAMP=%VENV_ROOT%\.requirements_stamp"
set "NEED_INSTALL="

if not exist "%REQ_FILE%" goto :no_requirements

REM --- silence Streamlit's first-run email prompt, which otherwise blocks -----
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit" >nul 2>&1
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    >"%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >>"%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

REM --- build the environment if this user does not have one yet --------------
if exist "%QT_PY%" goto :have_venv

echo.
echo   First run on this PC. Building your local Python environment.
echo     Location: %VENV_ROOT%
echo     Takes a minute or two. It happens once per machine.
echo.

set "BOOTSTRAP_PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "BOOTSTRAP_PY=py -3"
if not defined BOOTSTRAP_PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "BOOTSTRAP_PY=python"
)
if not defined BOOTSTRAP_PY goto :no_python

%BOOTSTRAP_PY% -m venv "%VENV_ROOT%"
if not exist "%QT_PY%" goto :venv_failed
set "NEED_INSTALL=1"

:have_venv
REM --- reinstall if requirements.txt has changed since the last install ------
set "REQ_HASH="
for /f "skip=1 delims=" %%h in ('certutil -hashfile "%REQ_FILE%" SHA256 2^>nul') do if not defined REQ_HASH set "REQ_HASH=%%h"
set "REQ_HASH=%REQ_HASH: =%"
set "OLD_HASH="
if exist "%STAMP%" for /f "usebackq delims=" %%h in ("%STAMP%") do set "OLD_HASH=%%h"
if not "%REQ_HASH%"=="%OLD_HASH%" set "NEED_INSTALL=1"

REM --- and if anything the apps import is missing ----------------------------
"%QT_PY%" -c "import streamlit, pandas, requests, msal, openpyxl" >nul 2>&1
if errorlevel 1 set "NEED_INSTALL=1"

if not defined NEED_INSTALL goto :ok

echo   Installing packages from requirements.txt ...
"%QT_PY%" -m pip install --upgrade pip --disable-pip-version-check -q
"%QT_PY%" -m pip install -r "%REQ_FILE%" --disable-pip-version-check
if errorlevel 1 goto :pip_failed
"%QT_PY%" -c "import streamlit, pandas, requests, msal, openpyxl" >nul 2>&1
if errorlevel 1 goto :pip_failed
>"%STAMP%" echo %REQ_HASH%
echo   Environment ready.
echo.

:ok
exit /b 0

:no_requirements
echo.
echo   requirements.txt was not found next to this launcher:
echo     %REQ_FILE%
echo   Your OneDrive copy of the Query tool folder may be incomplete. Open the
echo   folder in File Explorer, let OneDrive finish syncing, then try again.
echo.
exit /b 1

:no_python
echo.
echo   Python is not installed on this PC, or is not on PATH.
echo   Install Python 3.11 or later from the Company Portal, or from
echo   python.org, and tick "Add python.exe to PATH" during setup.
echo   Then run this launcher again. Nothing else needs configuring.
echo.
exit /b 1

:venv_failed
echo.
echo   Could not create the Python environment at:
echo     %VENV_ROOT%
echo   Check you can write to that folder, then run the launcher again.
echo.
exit /b 1

:pip_failed
echo.
echo   Package installation failed. Usual causes: no network, or the proxy
echo   blocked pypi.org. To retry from a clean slate, delete this folder and
echo   run the launcher again:
echo     %VENV_ROOT%
echo.
exit /b 1
