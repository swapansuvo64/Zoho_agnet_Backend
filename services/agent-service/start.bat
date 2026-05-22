@echo off
cd /d "%~dp0"
echo Starting Zoho Agent Backend on Windows...
if not exist "venv\Scripts\python.exe" (
    echo Virtual environment 'venv' not found or python.exe is missing.
    echo Please make sure the venv is created.
    pause
    exit /b 1
)
echo Checking for existing process on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo Found process %%a on port 8000. Killing it to start fresh...
    taskkill /f /pid %%a
)

echo Starting FastAPI server...
venv\Scripts\python.exe -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
pause
