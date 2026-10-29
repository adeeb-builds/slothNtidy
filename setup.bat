@echo off
setlocal
cd /d "%~dp0"
title slothNtidy setup
echo.
echo  ============================================================
echo   slothNtidy - one-time setup (needs internet, about 5-10 min)
echo  ============================================================
echo.

rem ---- 1. Python -------------------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY goto :nopython
%PY% --version
if errorlevel 1 goto :nopython

rem ---- 2. Private Python environment for this project -----------------------
if not exist ".venv\Scripts\activate.bat" (
    echo [1/5] Creating the project environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
)
call ".venv\Scripts\activate.bat"

rem ---- 3. Libraries ---------------------------------------------------------
echo [2/5] Installing libraries (the AI library is the big one)...
python -m pip install --upgrade pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

rem ---- 4. The local AI model (downloaded once, then works offline) ----------
echo [3/5] Downloading the MiniLM model (about 90 MB, one time only)...
python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2'); print('MiniLM ready')"
if errorlevel 1 echo     (Model download failed - the app still works using keyword matching. Run setup.bat again later.)

rem ---- 5. Tesseract OCR (reads photos of handwritten notes) -----------------
echo [4/5] Checking Tesseract OCR...
python -c "import sys; from config import configure_tesseract as c; sys.exit(0 if c() else 1)"
if errorlevel 1 call :tesseract

rem ---- 6. Self-check --------------------------------------------------------
echo [5/5] Running the self-check...
python -m pytest -q
echo.
echo  ============================================================
echo   Setup complete. Double-click run.bat to start slothNtidy.
echo  ============================================================
pause
exit /b 0

:tesseract
echo     Tesseract is not installed. Installing it with winget (click Yes if Windows asks)...
winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo     Automatic install did not work. Opening the download page:
    echo     download the 64-bit installer, run it, keep the default folder, then run setup.bat again.
    start "" https://github.com/UB-Mannheim/tesseract/wiki
)
exit /b 0

:nopython
echo Python was not found.
echo Install Python 3.12 from the page that is opening now.
echo IMPORTANT: on the first installer screen tick "Add python.exe to PATH".
echo Then double-click setup.bat again.
start "" https://www.python.org/downloads/windows/
pause
exit /b 1

:fail
echo.
echo Setup stopped because of an error. Scroll up, take a screenshot of the red text and send it to Claude.
pause
exit /b 1
