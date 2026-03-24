@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "VENV_PYTHON=%BACKEND_DIR%\venv\Scripts\python.exe"

echo Starting Gas Incident Intelligence Backend...
echo.

if not exist "%VENV_PYTHON%" (
    echo ERROR: Virtual environment not found at "%VENV_PYTHON%".
    echo Please run:
    echo   cd /d "%BACKEND_DIR%"
    echo   python -m venv venv
    echo   venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

echo Checking backend dependencies...
"%VENV_PYTHON%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Backend dependencies are missing in the virtual environment.
    echo Please run:
    echo   cd /d "%BACKEND_DIR%"
    echo   venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

echo.
echo Starting FastAPI server...
cd /d "%BACKEND_DIR%"
"%VENV_PYTHON%" -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
