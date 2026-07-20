@echo off
setlocal
cd /d "%~dp0"
set "FACEFINDER_INSTALL_DIR=%~dp0"
set "FACEFINDER_DATA_DIR=%LOCALAPPDATA%\FaceFinder"
set "FACEFINDER_MODEL_DIR=%~dp0data\insightface"
set "INSIGHTFACE_HOME=%~dp0data\insightface"
"%~dp0runtime\python.exe" "%~dp0launcher.pyw"
pause
endlocal
