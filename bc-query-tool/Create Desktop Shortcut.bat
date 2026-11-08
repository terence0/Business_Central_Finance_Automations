@echo off
REM Creates a desktop shortcut to the Query Tool menu for the current user.
setlocal
set "TARGET=%~dp0QueryTool.bat"
set "LINK=%USERPROFILE%\Desktop\Contoso Query Tool.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LINK%');" ^
  "$s.TargetPath='%TARGET%';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.IconLocation='%SystemRoot%\System32\shell32.dll,220';" ^
  "$s.Description='Contoso Group Business Central Query Tool';" ^
  "$s.Save()"

if exist "%LINK%" (
    echo   Shortcut created on your desktop: Contoso Query Tool
) else (
    echo   Could not create the shortcut. You can drag QueryTool.bat to your
    echo   desktop with the right mouse button and choose "Create shortcuts here".
)
echo.
pause
endlocal
