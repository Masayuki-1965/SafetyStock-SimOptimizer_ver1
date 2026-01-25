@echo off
REM Kill any running SafetyStock-SimOptimizer_ver1.exe processes
echo Killing SafetyStock-SimOptimizer_ver1.exe if running...
taskkill /F /IM SafetyStock-SimOptimizer_ver1.exe >nul 2>&1
if %errorlevel% equ 0 (
    echo Process killed.
) else (
    echo No running process found.
)
timeout /t 2 >nul
echo Ready to rebuild.
