@echo off
rem ===========================================================================
rem  Shared include: works out PROJECT_DIR for a project inside the Global
rem  Finance library, without hardcoding any absolute path.
rem
rem  Usage, right after "setlocal":
rem
rem      call "%~dp0_find_project.cmd" "Finance Systems\Automations\bc-query-tool" "vatRecon.py" || (pause & exit /b 1)
rem      ...
rem      cd /d "%PROJECT_DIR%"
rem
rem  Arg 1: the project's path relative to the library root.
rem  Arg 2: a file that must exist inside it, used to confirm the match.
rem
rem  Why this exists. The synced path differs from person to person:
rem    - the OneDrive root may carry a "(1)" suffix (anyone signed into two
rem      accounts gets one), or be absent entirely where the library was
rem      mapped straight under the user profile;
rem    - the library folder is "Documents - Finance" for some people
rem      and "Finance - Documents" for others, depending on how
rem      SharePoint set the sync up.
rem  Launchers that spelled the library out therefore worked for one person
rem  and failed for the next. The OneDrive / OneDriveCommercial environment
rem  variables are no help either - they can point at a different root from
rem  the one actually holding the library.
rem
rem  These launchers live at
rem      <library>\Finance Systems\Automations\launchers\
rem  so the library root is three levels up from this include; that is tried
rem  first and needs no guessing at all. Should a launcher be copied out of
rem  the folder, the likely roots are then searched for the folder *layout*
rem  rather than for any particular name.
rem ===========================================================================

set "PROJECT_DIR="
set "_FP_SUB=%~1"
set "_FP_MARKER=%~2"

if "%_FP_SUB%"=="" (
    echo   [_find_project] No project subpath was given.
    exit /b 1
)

rem --- 1. relative to these launchers ---------------------------------------
for %%R in ("%~dp0..\..\..") do call :_fp_try "%%~fR"

rem --- 2. fallback: this launcher has been copied elsewhere ------------------
if not defined PROJECT_DIR call :_fp_try "%USERPROFILE%"
if not defined PROJECT_DIR call :_fp_libs "%USERPROFILE%"
if not defined PROJECT_DIR for /d %%R in ("%USERPROFILE%\OneDrive*") do call :_fp_libs "%%~R"

if not defined PROJECT_DIR (
    echo.
    echo   Could not find this automation's project folder:
    echo     %_FP_SUB%
    echo.
    echo   These launchers normally sit in
    echo     ...\Finance Systems\Automations\launchers\
    echo   and locate the project from there.
    echo.
    echo   Either put this file back in that folder, or make sure the
    echo   "Finance" library has finished syncing in OneDrive - look
    echo   for the green ticks in File Explorer - and try again.
    echo.
    exit /b 1
)

exit /b 0

rem ---------------------------------------------------------------------------
:_fp_libs
rem Try each library-looking folder under the given root, whatever its name.
if defined PROJECT_DIR goto :eof
for /d %%L in ("%~1\*Global Finance*") do call :_fp_try "%%~L"
goto :eof

:_fp_try
rem Accept the candidate library root if the marker file is where we expect.
if defined PROJECT_DIR goto :eof
if exist "%~1\%_FP_SUB%\%_FP_MARKER%" for %%P in ("%~1\%_FP_SUB%") do set "PROJECT_DIR=%%~fP"
goto :eof
