@echo off
REM General Ledger Query tool. Double-click to run.
echo.
echo   Reminder for the tax GL pull: set the start date back to 2015-01-01 or
echo   earlier. A short start date drops the opening-balance journals and the
echo   liability will not tie.
call "%~dp0_launch.bat" app.py 8502 "General Ledger Query"
