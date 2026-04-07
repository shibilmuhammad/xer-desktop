@echo off
echo.
echo ==========================================
echo   XER Assistant Windows Setup Script
echo ==========================================
echo.

:: 1. Main Directory
echo [1/4] Installing root dependencies...
call npm install
if %errorlevel% neq 0 (
    echo Error installing root dependencies.
    exit /b %errorlevel%
)

:: 2. Frontend Directory
echo [2/4] Installing frontend dependencies...
cd frontend
call npm install
cd ..
if %errorlevel% neq 0 (
    echo Error installing frontend dependencies.
    exit /b %errorlevel%
)

:: 3. Electron Directory
echo [3/4] Installing electron dependencies...
cd electron
call npm install
cd ..
if %errorlevel% neq 0 (
    echo Error installing electron dependencies.
    exit /b %errorlevel%
)

:: 4. Python Virtual Environment
echo [4/4] Setting up Python virtual environment...
if not exist "venv_desktop" (
    python -m venv venv_desktop
    echo Virtual environment 'venv_desktop' created.
)

echo.
echo Installing Python backend dependencies...
venv_desktop\Scripts\python.exe -m pip install -r backend/requirements.txt
if %errorlevel% neq 0 (
    echo Error installing Python dependencies.
    exit /b %errorlevel%
)

echo.
echo ==========================================
echo   Setup Complete! 
echo.
echo   You can now start the application by running:
echo   npm run dev
echo ==========================================
pause
