@echo off
setlocal
title Install slothNtidy
cd /d "%TEMP%"
set "DEST=%LOCALAPPDATA%\slothNtidy"
set "ZIPURL=https://github.com/adeeb-builds/slothNtidy/archive/refs/heads/main.zip"

echo.
echo  =============================================================
echo   slothNtidy installer  -  sorts WhatsApp notes by syllabus
echo   Needs internet once (about 600 MB, 10-15 minutes).
echo   After that it works fully offline.
echo  =============================================================
echo.

echo [1/3] Downloading slothNtidy...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue';" ^
  "$zip = Join-Path $env:TEMP 'slothNtidy-download.zip';" ^
  "Invoke-WebRequest -UseBasicParsing '%ZIPURL%' -OutFile $zip;" ^
  "$dest = '%DEST%'; New-Item -ItemType Directory -Force -Path $dest | Out-Null;" ^
  "if (Test-Path (Join-Path $dest 'app')) { Remove-Item (Join-Path $dest 'app') -Recurse -Force };" ^
  "Expand-Archive $zip -DestinationPath $dest -Force;" ^
  "Rename-Item (Join-Path $dest 'slothNtidy-main') 'app';" ^
  "Remove-Item $zip -Force"
if errorlevel 1 goto :fail

echo [2/3] Setting up (libraries, AI model, OCR)...
call "%DEST%\app\setup.bat"
if errorlevel 1 goto :fail

echo [3/3] Adding slothNtidy to your Desktop and Start menu...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$app = '%DEST%\app'; $sh = New-Object -ComObject WScript.Shell;" ^
  "foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {" ^
  "  $s = $sh.CreateShortcut((Join-Path $dir 'slothNtidy.lnk'));" ^
  "  $s.TargetPath = (Join-Path $app 'run.bat'); $s.WorkingDirectory = $app;" ^
  "  $s.IconLocation = (Join-Path $app 'assets\slothNtidy.ico'); $s.Description = 'Sort WhatsApp notes by syllabus';" ^
  "  $s.Save() }"

echo.
echo  =============================================================
echo   Done! Double-click the slothNtidy icon on your Desktop
echo   (the pixel sloth) whenever you want to sort your notes.
echo  =============================================================
echo.
choice /c YN /m "Start slothNtidy now"
if errorlevel 2 exit /b 0
start "" "%DEST%\app\run.bat"
exit /b 0

:fail
echo.
echo Installation stopped because of an error. Take a screenshot of this window
echo and open an issue at https://github.com/adeeb-builds/slothNtidy/issues
pause
exit /b 1
