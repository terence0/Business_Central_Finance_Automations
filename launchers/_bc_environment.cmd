@echo off
rem ===========================================================================
rem  Shared include: which Business Central environment a launcher uses.
rem
rem  Every automation has two run files:
rem      Production\Run <name>.bat              Production
rem      Sandbox\Run <name> (Sandbox).bat       the sandbox below
rem  The sandbox one just calls the Production one with the word "sandbox",
rem  so the two can never drift apart.
rem
rem  Usage, right after "setlocal" in a run file:
rem      call "%~dp0..\_bc_environment.cmd" "%~1"
rem
rem  Sets, for the app it starts (they read BC_ENVIRONMENT_NAME):
rem      BC_ENVIRONMENT_NAME   Production, or the sandbox name below
rem      BC_PORT_OFFSET        0 for Production, 100 for the sandbox, so both
rem                            can be open at the same time
rem      BC_IS_SANDBOX         1 in the sandbox, 0 in Production
rem
rem  WHEN THE SANDBOX IS REFRESHED UNDER A NEW NAME, CHANGE THIS ONE LINE:
set "BC_SANDBOX_NAME=Sandbox_Test"
rem ===========================================================================

if /i "%~1"=="sandbox" (
    set "BC_ENVIRONMENT_NAME=%BC_SANDBOX_NAME%"
    set "BC_PORT_OFFSET=100"
    set "BC_IS_SANDBOX=1"
    color 2F
) else (
    set "BC_ENVIRONMENT_NAME=Production"
    set "BC_PORT_OFFSET=0"
    set "BC_IS_SANDBOX=0"
)

echo ===========================================================================
if "%BC_IS_SANDBOX%"=="1" (
    echo    SANDBOX  ^|  Business Central environment: %BC_ENVIRONMENT_NAME%
    echo    Nothing done in this window affects Production.
) else (
    echo    PRODUCTION  ^|  Business Central environment: Production
)
echo ===========================================================================
echo.
exit /b 0
