@echo off
echo.
echo ==========================================
echo   XER Assistant Enterprise Builder
echo ==========================================
echo.

:: 1. Compile Python Backend
echo [1/3] Compiling Python Backend (PyInstaller)...
cd backend
if not exist "venv_desktop\Scripts\activate.bat" (
   :: Make sure we use the root venv
   cd ..
   set PYTHON_VENV=venv_desktop\Scripts\python.exe
   cd backend
) else (
   set PYTHON_VENV=..\venv_desktop\Scripts\python.exe
)

:: Ensure pyinstaller is installed
%PYTHON_VENV% -m pip install pyinstaller

:: Build executable to dist/backend
%PYTHON_VENV% -m PyInstaller --name backend --onefile --noconsole main.py
if %errorlevel% neq 0 (
    echo Error compiling Python backend.
    exit /b %errorlevel%
)
cd ..

:: 2. Build React Frontend
echo [2/3] Building React Frontend...
cd frontend
call npm run build
if %errorlevel% neq 0 (
    echo Error building frontend.
    exit /b %errorlevel%
)
cd ..

:: 3. Package Electron Application
echo [3/3] Packaging Electron Application...
cd electron
:: Ensure electron-builder is installed locally if not in package.json
call npm install electron-builder --save-dev
call npx electron-builder --win
if %errorlevel% neq 0 (
    echo Error packaging Electron application.
    exit /b %errorlevel%
)
cd ..

echo.
echo ==========================================
echo   Build Complete! 
echo   Installer can be found in electron/dist/
echo ==========================================
pause
