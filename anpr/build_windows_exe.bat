@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo This builds a standalone PlateReader.exe that you can copy, together
echo with config.example.yaml, to any Windows PC (no Python needed there).
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install it first from https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

pip install pyinstaller

echo.
echo Building PlateReader.exe ...
pyinstaller --noconfirm --onefile --console --name PlateReader run.py

if not exist "dist\PlateReader.exe" (
    echo Building the exe failed - check the messages above.
    pause
    exit /b 1
)

copy config.example.yaml dist\ >nul
echo.
echo Done. The dist folder now has two files:
echo   PlateReader.exe
echo   config.example.yaml
echo Copy both of these together to any Windows PC (even without Python) and run PlateReader.exe.
pause
