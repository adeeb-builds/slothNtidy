@echo off
cd /d "%~dp0"
title slothNtidy
if not exist ".venv\Scripts\activate.bat" (
    echo slothNtidy is not set up yet. Double-click setup.bat first.
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"
echo Starting slothNtidy... your browser will open in a few seconds.
echo Keep this window open while you use the app. Close it to stop slothNtidy.
start "" cmd /c "timeout /t 5 /nobreak >nul & start http://localhost:8501"
python -m streamlit run app.py
pause
