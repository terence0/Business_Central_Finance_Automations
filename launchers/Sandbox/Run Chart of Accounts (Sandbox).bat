@echo off
rem Sandbox version of "..\Production\Run Chart of Accounts.bat": the same automation, against the
rem Business Central sandbox named in _bc_environment.cmd, on its own port
rem (+100) so it can run alongside Production.
call "%~dp0..\Production\Run Chart of Accounts.bat" sandbox
exit /b %ERRORLEVEL%
