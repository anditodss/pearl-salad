@echo off
setlocal
echo ==============================================
echo Salad Fleet Manager - 1-Click Startup
echo ==============================================
echo.

:: Set working directory to the location of the script
cd /d "%~dp0"

:: 1. Check Python installation
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in PATH! Please install Python 3.9+.
    pause
    exit /b
)

:: 2. Check Node.js installation
node --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH! Please install Node.js 18+.
    pause
    exit /b
)

:: 3. Setup Python Virtual Environment
if not exist "venv\" (
    echo [1/5] Creating Python virtual environment...
    python -m venv venv
) else (
    echo [1/5] Python virtual environment found.
)

:: 4. Install Python Dependencies
echo [2/5] Installing/updating Python dependencies (this might take a minute)...
call venv\Scripts\activate.bat
pip install -r requirements.txt

:: 5. Create config templates if missing
echo [3/5] Checking configuration files...
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo       Created .env from template.
    )
)
if not exist "config.json" (
    if exist "config.json.example" (
        copy config.json.example config.json >nul
        echo       Created config.json from template.
    )
)

:: 6. Install Node dependencies
echo [4/5] Checking UI dependencies...
pushd ui
if not exist "node_modules\" (
    echo       Installing Node.js dependencies (this might take a few minutes)...
    call npm install
) else (
    echo       Node.js dependencies found.
)
popd

:: 7. Start Servers
echo [5/5] Starting Servers...
echo.

:: Start Backend (Keeps window open on crash for debugging)
start "Backend (FastAPI)" cmd /k "call venv\Scripts\activate.bat && python -m uvicorn app:app --host 0.0.0.0 --port 8000"

:: Start Frontend (Keeps window open on crash for debugging)
start "Frontend (Next.js)" cmd /k "cd ui && npm run dev"

echo ==============================================
echo ALL DONE! 
echo.
echo The backend is running in a separate window.
echo The frontend is running in a separate window.
echo.
echo Please wait a few seconds, then open your browser to:
echo http://localhost:3000
echo.
echo You can safely close this launcher window.
echo ==============================================
pause
