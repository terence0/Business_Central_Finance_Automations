@echo off
REM ===========================================================================
REM  _launch.bat        Finance Query Tool
REM
REM  Shared launcher.  Usage:  call _launch.bat <script.py> <port> "<title>"
REM
REM  Root paths: every path used by this tool is worked out from the location of
REM  this file (%~dp0), never from a user name or a OneDrive folder name. The
REM  apps and query.py read .\config\config.json and write .\logging\ and
REM  .\GL Query\JSON\ as paths relative to the current directory, so the cd
REM  below is what makes those resolve. Copy this folder anywhere, on any PC,
REM  under any user, and it still works.
REM ===========================================================================

set "APP_SCRIPT=%~1"
set "APP_PORT=%~2"
set "APP_TITLE=%~3"

REM --- Production or sandbox --------------------------------------------------
REM The run files in "launchers" set BC_ENVIRONMENT_NAME and
REM BC_PORT_OFFSET (see _bc_environment.cmd there). The apps read the
REM environment through config\bc_env.py; the sandbox opens on its own port
REM (+100) so Production and sandbox can be open side by side.
if not defined BC_ENVIRONMENT_NAME set "BC_ENV_SHOWN=as in config.json (Production)"
if defined BC_ENVIRONMENT_NAME set "BC_ENV_SHOWN=%BC_ENVIRONMENT_NAME%"
if defined BC_PORT_OFFSET set /a APP_PORT=%APP_PORT%+%BC_PORT_OFFSET%

cd /d "%~dp0"

echo ===========================================================================
echo   Contoso Group  ^|  %APP_TITLE%
echo ===========================================================================
echo   Folder: %~dp0
echo   Business Central environment: %BC_ENV_SHOWN%
echo.

REM --- preflight: the files and folders the apps expect ----------------------
if not exist "%~dp0%APP_SCRIPT%" goto :no_script
if not exist "%~dp0config\config.json" goto :no_config
if not exist "%~dp0logging" mkdir "%~dp0logging" >nul 2>&1
if not exist "%~dp0GL Query\JSON" mkdir "%~dp0GL Query\JSON" >nul 2>&1

REM --- environment ----------------------------------------------------------
call "%~dp0_venv_setup.bat"
if errorlevel 1 goto :end

REM --- run ------------------------------------------------------------------
echo   Starting. Your browser will open at http://localhost:%APP_PORT%
echo   Leave this window open while you use the tool.
echo   Close it, or press Ctrl+C, when you are finished.
echo.

"%QT_PY%" -m streamlit run "%APP_SCRIPT%" --server.port %APP_PORT% --browser.gatherUsageStats false
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo   The app stopped with code %RC%.
    echo   If it says the port is already in use, this tool is already running
    echo   in another window. Use that window, or close it and start again.
    echo   Otherwise read the message above and send it to the system owner.
)
goto :end

:no_script
echo.
echo   %APP_SCRIPT% is missing from this folder.
echo   Your OneDrive copy is incomplete. Let it finish syncing and try again.
echo.
goto :end

:no_config
echo.
echo   config\config.json is missing from this folder.
echo   The tool cannot reach Business Central without it. Let OneDrive finish
echo   syncing this folder, then try again.
echo.
goto :end

:end
echo.
pause
exit /b %ERRORLEVEL%
