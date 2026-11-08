@echo off
setlocal

rem Planful Push Controller - opens in your browser.
rem
rem Runs the Planful connector Summary Transaction push across entities. In
rem Production it sends data on to Planful. In the sandbox, sending to Planful
rem is always switched off (the sandbox's Planful connector setup may point at live Planful);
rem the Business Central side still runs, for testing. Needs Python 3.12.
rem
rem Production / Sandbox: this file runs against Production. Its twin
rem "..\Sandbox\Run Planful Streamlit Project (Sandbox).bat" runs the same automation against the Business Central
rem sandbox named in _bc_environment.cmd, on port +100, so both can be open
rem at once. Nothing needs editing to switch.

call "%~dp0..\_bc_environment.cmd" "%~1"

call "%~dp0..\_find_project.cmd" "Finance Systems\Automations\planful-push-controller" "app.py" || (pause & exit /b 1)

call "%~dp0..\_find_py312.cmd" || (pause & exit /b 1)

call "%~dp0..\_ensure_venv.cmd" "planful-push-controller" "%PROJECT_DIR%\requirements.txt" "%PY312%" || (pause & exit /b 1)

set /a APP_PORT=8513+%BC_PORT_OFFSET%
title Planful Push Controller - %BC_ENVIRONMENT_NAME%
echo   Opening at http://localhost:%APP_PORT%
cd /d "%PROJECT_DIR%"
"%VENV_PY%" -m streamlit run app.py --server.port %APP_PORT% --browser.gatherUsageStats false
pause
