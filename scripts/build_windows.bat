@echo off
echo.
echo ==========================================
echo   XER Assistant Enterprise Builder
echo ==========================================
echo.

:: Set root directory relative to this script
set ROOT_DIR=%~dp0..
set PYTHON_VENV=%ROOT_DIR%\venv_desktop\Scripts\python.exe

:: 1. Compile Python Backend
echo [1/3] Compiling Python Backend (PyInstaller)...

if not exist "%PYTHON_VENV%" (
    echo Python virtual environment not found at %PYTHON_VENV%
    echo Please run setup_windows.bat first.
    exit /b 1
)

cd /d "%ROOT_DIR%\backend"

:: Ensure pyinstaller is installed
"%PYTHON_VENV%" -m pip install pyinstaller

:: Build executable to dist/backend
"%PYTHON_VENV%" -m PyInstaller --name backend --onefile --noconsole main.py
if %errorlevel% neq 0 (
    echo Error compiling Python backend.
    exit /b %errorlevel%
)
cd /d "%ROOT_DIR%"

:: 2. Build React Frontend
echo [2/3] Building React Frontend...
cd /d "%ROOT_DIR%\frontend"
call npm run build
if %errorlevel% neq 0 (
    echo Error building frontend.
    exit /b %errorlevel%
)
cd /d "%ROOT_DIR%"

:: 3. Package Electron Application
echo [3/3] Packaging Electron Application...
cd /d "%ROOT_DIR%\electron"
:: Ensure electron-builder is installed locally if not in package.json
call npm install electron-builder --save-dev
call npx electron-builder --win
if %errorlevel% neq 0 (
    echo Error packaging Electron application.
    exit /b %errorlevel%
)
cd /d "%ROOT_DIR%"

echo.
echo ==========================================
echo   Build Complete! 
echo   Installer can be found in electron/dist/
echo ==========================================
pause
