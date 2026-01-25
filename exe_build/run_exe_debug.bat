@echo off
REM Run the built EXE from cmd to see any error messages.
cd /d "%~dp0dist\SafetyStock-SimOptimizer_ver1"
echo Running EXE from: %CD%
echo.
SafetyStock-SimOptimizer_ver1.exe
echo.
echo EXE exited. errorlevel=%errorlevel%
pause
