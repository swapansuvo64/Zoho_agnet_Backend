@echo off
cd /d "%~dp0"
echo Starting Zoho Agent Auth Service on Windows...
if not exist "venv\Scripts\python.exe" (
    echo Virtual environment 'venv' not found or python.exe is missing.
    echo Please make sure the venv is created.
    pause
    exit /b 1
)

echo Checking for existing process on port 8001...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8001 ^| findstr LISTENING') do (
    echo Found process %%a on port 8001. Killing it to start fresh...
    taskkill /f /pid %%a
)

echo Starting FastAPI server on port 8001...
venv\Scripts\python.exe -m uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
pause
