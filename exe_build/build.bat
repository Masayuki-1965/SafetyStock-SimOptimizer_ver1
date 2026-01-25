@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo SafetyStock-SimOptimizer EXE Build
echo ============================================
echo.
echo TIP: Run from cmd (cd to this folder, then build.bat) so the
echo      window stays open. Double-click may close it when done.
echo.

echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    pause
    exit /b 1
)
python --version
echo.

echo [2/5] Creating venv...
if exist venv (
    echo venv exists. Skipping.
) else (
    py -3.11 -m venv venv
    if errorlevel 1 (
        echo ERROR: venv creation failed.
        pause
        exit /b 1
    )
    echo venv created.
)
echo.

echo [3/5] Activating venv...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: venv activation failed.
    pause
    exit /b 1
)
echo venv activated.
echo.

echo [4/5] Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)
echo Dependencies installed.
echo.

echo [5/5] Running PyInstaller...
REM Kill any running EXE first (otherwise dist deletion fails)
taskkill /F /IM SafetyStock-SimOptimizer_ver1.exe >nul 2>&1
timeout /t 1 >nul
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo.

set "DIST_PATH=%~dp0dist"
set "BUILD_PATH=%~dp0build"

echo Building... (log: build_log.txt). Wait 15-20 min.
echo PYZ / EXE / COLLECT run after "reclassification".
echo.
python -u -m PyInstaller SafetyStock-SimOptimizer_ver1.spec --clean --noconfirm --distpath "%DIST_PATH%" --workpath "%BUILD_PATH%" > build_log.txt 2>&1
set PYERR=!errorlevel!

if !PYERR! neq 0 (
    echo.
    echo ERROR: Build failed. errorlevel=!PYERR!
    echo --- Last 60 lines of build_log.txt ---
    if exist build_log.txt powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content build_log.txt -Tail 60"
    echo ---
    pause
    exit /b 1
)

echo.
echo ============================================
echo Build done.
echo ============================================
echo.

if exist "%DIST_PATH%\SafetyStock-SimOptimizer_ver1" (
    echo SUCCESS. Output: %DIST_PATH%\SafetyStock-SimOptimizer_ver1
    dir /b "%DIST_PATH%\SafetyStock-SimOptimizer_ver1"
) else (
    echo WARN: dist folder is empty.
    echo --- Last 80 lines of build_log.txt ---
    if exist build_log.txt powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content build_log.txt -Tail 80"
    echo ---
)

echo.
deactivate 2>nul
echo Log saved: build_log.txt
echo Next: run %DIST_PATH%\SafetyStock-SimOptimizer_ver1\SafetyStock-SimOptimizer_ver1.exe
echo.
pause
