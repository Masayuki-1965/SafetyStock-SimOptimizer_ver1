@echo off
REM Minimal build: run this AFTER activating venv and installing deps.
REM Usage: open cmd, cd to this folder, run: venv\Scripts\activate, then build_minimal.bat
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "DIST_PATH=%SCRIPT_DIR%dist"
set "BUILD_PATH=%SCRIPT_DIR%build"

echo Building with PyInstaller...
python -m PyInstaller SafetyStock-SimOptimizer_ver1.spec --clean --noconfirm --distpath "%DIST_PATH%" --workpath "%BUILD_PATH%" --specpath "%SCRIPT_DIR%"
if %errorlevel% neq 0 (
    echo Build failed. errorlevel=%errorlevel%
    pause
    exit /b 1
)

echo.
if exist "%DIST_PATH%\SafetyStock-SimOptimizer_ver1" (
    echo SUCCESS. See %DIST_PATH%\SafetyStock-SimOptimizer_ver1
) else (
    echo WARN: dist folder empty.
)
echo.
pause
