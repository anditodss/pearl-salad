@echo off
echo Starting Salad Fleet Manager...
echo.
echo [1/2] Starting FastAPI Backend on Port 8000...
start "Backend (FastAPI)" cmd /c "python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload"

echo [2/2] Starting Next.js Frontend on Port 3000...
cd ui
start "Frontend (Next.js)" cmd /c "npm run dev"

echo.
echo Both servers are booting up!
echo The Next.js dashboard will be available at http://localhost:3000
echo You can close this window now. The servers are running in separate terminal windows.
pause
