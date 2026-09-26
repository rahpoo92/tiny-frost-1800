@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on this system.
    echo Please install Python 3.11 or newer from the link below.
    echo During setup, make sure to check "Add python.exe to PATH".
    echo.
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Setting up the app for the first time, please wait...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create the app environment.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 (
        echo Failed to install required packages. Check your internet connection.
        pause
        exit /b 1
    )
) else (
    call .venv\Scripts\activate.bat
)

if not exist "config.yaml" (
    copy config.example.yaml config.yaml >nul
    echo Settings file created: config.yaml
    echo Notepad will open - set your camera source, then save and close it to continue.
    pause
    notepad config.yaml
)

python run.py
if errorlevel 1 (
    echo The app stopped with an error - see the message above.
    pause
)
