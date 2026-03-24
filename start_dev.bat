@echo off
setlocal
echo ========================================
echo Gas Incident Intelligence Platform
echo Development Environment Startup
echo ========================================
echo.

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"
set "BACKEND_PYTHON=%BACKEND_DIR%\venv\Scripts\python.exe"

echo [1/3] Checking Backend...
cd /d "%BACKEND_DIR%"
if not exist "%BACKEND_PYTHON%" (
    echo ERROR: Virtual environment not found!
    echo Please run: python -m venv venv
    echo Then run: venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

"%BACKEND_PYTHON%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Backend dependencies are missing!
    echo Please run: venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo [2/3] Starting Backend Server...
start "Backend Server" cmd /k "cd /d %BACKEND_DIR% && venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 5020"

echo Waiting for backend to start...
timeout /t 5 /nobreak > nul

echo [3/3] Starting Frontend...
cd /d "%FRONTEND_DIR%"
if not exist "node_modules" (
    echo Installing frontend dependencies...
    call npm install
)

start "Frontend Dev Server" cmd /k "cd /d %CD% && npm run dev"

echo.
echo ========================================
echo Both servers are starting!
echo ========================================
echo Backend:  http://localhost:5020
echo Frontend: http://localhost:3000
echo.
echo Press any key to close this window...
echo (The servers will continue running in separate windows)
pause > nul
