@echo off
REM ===========================================================================
REM  QueryTool.bat        Finance Query Tool
REM  Single entry point. Pick a tool from the menu.
REM  Anyone in the finance team can run this. Nothing to install or configure
REM  beyond Python being present on the PC.
REM ===========================================================================
title Contoso Group Query Tool

:menu
cls
echo ===========================================================================
echo    CONTOSO GROUP  ^|  BUSINESS CENTRAL QUERY TOOL
echo ===========================================================================
if defined BC_ENVIRONMENT_NAME (
    echo    Business Central environment: %BC_ENVIRONMENT_NAME%
) else (
    echo    Business Central environment: Production ^(from config.json^)
)
echo.
echo    1.  Fixed Asset Listing
echo    2.  General Ledger Query
echo    3.  Trial Balance
echo    4.  VAT Return and Recon
echo    5.  Customer Ageing (debtors ageing and ECL)
echo    6.  Chart of Accounts (add G/L accounts to every entity)
echo.
echo    7.  Create a desktop shortcut to this menu
echo    8.  Repair the Python environment on this PC
echo.
echo    0.  Exit
echo.
set "CHOICE="
set /p "CHOICE=   Enter a number then press Enter: "

if "%CHOICE%"=="1" goto :fixedassets
if "%CHOICE%"=="2" goto :gl
if "%CHOICE%"=="3" goto :tb
if "%CHOICE%"=="4" goto :vatrecon
if "%CHOICE%"=="5" goto :ageing
if "%CHOICE%"=="6" goto :coa
if "%CHOICE%"=="7" goto :shortcut
if "%CHOICE%"=="8" goto :repair
if "%CHOICE%"=="0" exit /b 0
goto :menu

:fixedassets
call "%~dp0_launch.bat" fixedAssets.py 8501 "Fixed Asset Listing"
goto :menu

:gl
echo.
echo   Reminder for the tax GL pull: set the start date back to 2015-01-01 or
echo   earlier. A short start date drops the opening-balance journals and the
echo   liability will not tie.
call "%~dp0_launch.bat" app.py 8502 "General Ledger Query"
goto :menu

:tb
call "%~dp0_launch.bat" trialBalance.py 8503 "Trial Balance Query"
goto :menu

:vatrecon
echo.
echo   Extracts, classifies and publishes one VAT recon workbook per selected
echo   entity per month to the shared VAT Recon Report Files folder. An
echo   existing file for the same entity/month is overwritten.
call "%~dp0_launch.bat" vatRecon.py 8504 "VAT Return and Recon"
goto :menu

:ageing
echo.
echo   Aged on due date. Balances are rebuilt to the cut-off from detailed
echo   ledger entries, so the answer is the same whenever you run it. For the
echo   year end set the cut-off to 31 August. Save the file into
echo   2. Supporting Workings\Debtor aging workings.
call "%~dp0_launch.bat" CustomerAgeing.py 8505 "Customer Ageing Extract"
goto :menu

:coa
echo.
echo   Runs against the SANDBOX Sandbox_Test, not Production. Writes to it
echo   only after you approve a dry run. Existing accounts are never changed.
call "%~dp0_launch.bat" coaSetup.py 8506 "Chart of Accounts"
goto :menu

:shortcut
call "%~dp0Create Desktop Shortcut.bat"
goto :menu

:repair
echo.
echo   Removing your local Python environment so it can be rebuilt.
echo   Nothing in OneDrive is touched.
echo.
if exist "%LOCALAPPDATA%\FinanceQueryTool\venv" rmdir /s /q "%LOCALAPPDATA%\FinanceQueryTool\venv"
call "%~dp0_venv_setup.bat"
echo.
pause
goto :menu
