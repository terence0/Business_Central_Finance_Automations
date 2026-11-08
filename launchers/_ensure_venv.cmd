@echo off
rem ===========================================================================
rem  Shared include: gives this user a private virtual environment for an
rem  automation, and keeps its packages in step with requirements.txt.
rem
rem  Usage, once PROJECT_DIR is known:
rem
rem      call "%~dp0_ensure_venv.cmd" "querytool" "%PROJECT_DIR%\requirements.txt" || (pause & exit /b 1)
rem      ...
rem      "%VENV_PY%" -m streamlit run app.py
rem
rem  Arg 1: venv key - the folder name the environment is kept under. Projects
rem         sharing a key share an environment, which is fine when they share
rem         a requirements.txt.
rem  Arg 2: path to that project's requirements.txt.
rem  Arg 3: optional. Interpreter to build the environment with, for projects
rem         pinned to a version - e.g. "%PY312%" from _find_py312.cmd.
rem
rem  Sets VENV_PY to the environment's python.exe.
rem
rem  Environments live under %LOCALAPPDATA%, deliberately outside OneDrive: a
rem  venv is not portable, because its activate script hardcodes the absolute
rem  path of the machine that created it. Syncing one would break everyone
rem  else's.
rem
rem  A SHA256 stamp of requirements.txt is kept beside the environment and
rem  compared on every run. Without it, an environment built before a
rem  dependency was added is never updated: the launcher only ever checked
rem  whether the folder existed, so a colleague would keep running stale
rem  packages and hit an import error far from the real cause.
rem ===========================================================================

set "VENV_PY="
set "_EV_KEY=%~1"
set "_EV_REQ=%~2"
set "_EV_CREATOR=%~3"
if not defined _EV_CREATOR set "_EV_CREATOR=python"

if "%_EV_KEY%"=="" (
    echo   [_ensure_venv] No venv key was given.
    exit /b 1
)

set "_EV_DIR=%LOCALAPPDATA%\FinanceAutomations\venvs\%_EV_KEY%"
set "VENV_PY=%_EV_DIR%\Scripts\python.exe"
set "_EV_STAMP=%_EV_DIR%\.requirements_stamp"
set "_EV_NEED="

rem --- silence Streamlit's first-run email prompt, which otherwise blocks ----
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit" >nul 2>&1
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    >"%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >>"%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

if not exist "%VENV_PY%" (
    echo.
    echo   First run of this automation on this PC. Building your private
    echo   Python environment - a minute or two, once per machine.
    echo     %_EV_DIR%
    echo.
    "%_EV_CREATOR%" -m venv "%_EV_DIR%"
    set "_EV_NEED=1"
)

if not exist "%VENV_PY%" (
    echo.
    echo   Could not create the Python environment at:
    echo     %_EV_DIR%
    echo   Check you can write to that folder, then try again.
    echo.
    exit /b 1
)

if not exist "%_EV_REQ%" goto :_ev_done

rem --- reinstall when requirements.txt has changed since the last install ---
set "_EV_HASH="
for /f "skip=1 delims=" %%h in ('certutil -hashfile "%_EV_REQ%" SHA256 2^>nul') do if not defined _EV_HASH set "_EV_HASH=%%h"
set "_EV_HASH=%_EV_HASH: =%"
set "_EV_OLD="
if exist "%_EV_STAMP%" for /f "usebackq delims=" %%h in ("%_EV_STAMP%") do set "_EV_OLD=%%h"
if not "%_EV_HASH%"=="%_EV_OLD%" set "_EV_NEED=1"

if not defined _EV_NEED goto :_ev_done

echo   Installing packages from requirements.txt ...
"%VENV_PY%" -m pip install --upgrade pip --disable-pip-version-check -q
"%VENV_PY%" -m pip install -r "%_EV_REQ%" --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo   Package installation failed. Usually no network, or the proxy
    echo   blocked pypi.org - try again on the VPN. If it keeps failing,
    echo   delete this folder and run the launcher again to start clean:
    echo     %_EV_DIR%
    echo.
    exit /b 1
)
>"%_EV_STAMP%" echo %_EV_HASH%
echo   Environment ready.
echo.

:_ev_done
exit /b 0
