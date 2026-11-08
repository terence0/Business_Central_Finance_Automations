@echo off
setlocal

rem BC Cost Centre Dimension Automation - opens in your browser.
rem
rem Creates cost centre dimension values and default dimensions. Writes to
rem Business Central; Production is refused unless ALLOW_PRODUCTION_UPDATES=true
rem in its .env. Its dependencies need Python 3.12 specifically.
rem
rem Production / Sandbox: this file runs against Production. Its twin
rem "..\Sandbox\Run BC Cost Centre Dimension Automation (Sandbox).bat" runs the same automation against the Business Central
rem sandbox named in _bc_environment.cmd, on port +100, so both can be open
rem at once. Nothing needs editing to switch.

call "%~dp0..\_bc_environment.cmd" "%~1"

call "%~dp0..\_find_project.cmd" "Finance Systems\Automations\cost-centre-dimension-automation" "app.py" || (pause & exit /b 1)

call "%~dp0..\_find_py312.cmd" || (pause & exit /b 1)

call "%~dp0..\_ensure_venv.cmd" "bc_cost_center_dimension_automation" "%PROJECT_DIR%\requirements.txt" "%PY312%" || (pause & exit /b 1)

set /a APP_PORT=8511+%BC_PORT_OFFSET%
title BC Cost Centre Dimension Automation - %BC_ENVIRONMENT_NAME%
echo   Opening at http://localhost:%APP_PORT%
cd /d "%PROJECT_DIR%"
"%VENV_PY%" -m streamlit run app.py --server.port %APP_PORT% --browser.gatherUsageStats false
pause
