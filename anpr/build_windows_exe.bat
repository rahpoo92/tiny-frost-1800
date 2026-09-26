@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo این اسکریپت یک فایل PlateReader.exe مستقل می‌سازد که می‌توانید
echo آن را به همراه config.example.yaml روی هر سیستم ویندوزی کپی کنید
echo (نیازی به نصب پایتون روی آن سیستم مقصد نیست).
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo پایتون پیدا نشد. ابتدا از https://www.python.org/downloads/ نصب کنید.
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
echo در حال ساخت PlateReader.exe ...
pyinstaller --noconfirm --onefile --console --name PlateReader run.py

if not exist "dist\PlateReader.exe" (
    echo ساخت فایل exe با خطا مواجه شد؛ پیام‌های بالا را بررسی کنید.
    pause
    exit /b 1
)

copy config.example.yaml dist\ >nul
echo.
echo تمام شد. در پوشه‌ی dist دو فایل هست:
echo   PlateReader.exe
echo   config.example.yaml
echo این دو فایل را با هم به هر سیستم ویندوزی (حتی بدون پایتون) کپی کنید و PlateReader.exe را اجرا کنید.
pause
