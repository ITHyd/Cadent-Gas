@echo off
echo ========================================
echo Gas Incident Intelligence Platform
echo Development Environment Startup
echo ========================================
echo.

echo [1/3] Checking Backend...
cd backend
if not exist "venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found!
    echo Please run: python -m venv venv
    echo Then run: venv\Scripts\activate
    echo Then run: pip install -r requirements.txt
    pause
    exit /b 1
)

echo [2/3] Starting Backend Server...
start "Backend Server" cmd /k "cd /d %CD% && venv\Scripts\activate && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

echo Waiting for backend to start...
timeout /t 5 /nobreak > nul

cd ..

echo [3/3] Starting Frontend...
cd frontend
if not exist "node_modules" (
    echo Installing frontend dependencies...
    call npm install
)

start "Frontend Dev Server" cmd /k "cd /d %CD% && npm run dev"

echo.
echo ========================================
echo Both servers are starting!
echo ========================================
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:3000
echo.
echo Press any key to close this window...
echo (The servers will continue running in separate windows)
pause > nul
