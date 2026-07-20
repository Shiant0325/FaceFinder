@echo off
setlocal
cd /d "%~dp0"
PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_installer.ps1"
set "code=%ERRORLEVEL%"
echo.
if not "%code%"=="0" (
  echo FaceFinder installer build failed. Check build_logs\build.log
) else (
  echo FaceFinder installer build completed successfully.
  echo Output: dist\FaceFinder_Setup_Windows_x64.exe
)
pause
exit /b %code%
