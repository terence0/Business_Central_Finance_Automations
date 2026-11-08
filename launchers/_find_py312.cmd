@echo off
rem Shared include: locates a Python 3.12 interpreter and sets PY312 to its
rem full executable path. Any launcher that needs 3.12 specifically should
rem call it like this, right after "setlocal":
rem
rem     call "%~dp0_find_py312.cmd" || (pause & exit /b 1)
rem     ...
rem     "%PY312%" -m venv "%VENV_DIR%"
rem
rem Set PY312_EXE before calling to force a specific interpreter path
rem (useful for testing, or a machine with a non-standard install location).

set "PY312="

if defined PY312_EXE if exist "%PY312_EXE%" set "PY312=%PY312_EXE%"

rem Preferred: ask the Windows "py" launcher, which is what the version pin
rem actually relies on and what most python.org installs register.
if not defined PY312 (
    for /f "delims=" %%I in ('py -3.12 -c "import sys;print(sys.executable)" 2^>nul') do set "PY312=%%I"
)

rem Fallback: the "py" launcher itself can be missing (e.g. Microsoft Store
rem installs, or someone unticked it during setup) even though 3.12 is on
rem disk. Check the standard install locations directly.
if not defined PY312 (
    for %%P in (
        "%LocalAppData%\Programs\Python\Python312\python.exe"
        "%ProgramFiles%\Python312\python.exe"
        "C:\Python312\python.exe"
    ) do if not defined PY312 if exist %%P set "PY312=%%~fP"
)

if not defined PY312 (
    echo This automation needs Python 3.12 specifically, which was not found.
    echo.
    echo Interpreters the Windows launcher can see on this machine:
    py -0p 2>nul
    if errorlevel 1 echo   [the "py" launcher itself is not installed]
    echo.
    echo Please install Python 3.12 from https://python.org - the "Downloads"
    echo page has older releases further down since 3.12 isn't the newest
    echo release anymore. During setup, keep "py launcher" ticked - that is
    echo what lets this script find it automatically. You can keep any other
    echo Python version already installed; this one is additional.
    exit /b 1
)

exit /b 0
