@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo پایتون روی این سیستم پیدا نشد.
    echo لطفا از آدرس زیر پایتون نسخه ۳.۱۱ یا بالاتر را نصب کنید.
    echo هنگام نصب، حتما تیک "Add python.exe to PATH" را بزنید.
    echo.
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo در حال آماده‌سازی برنامه برای اولین بار، لطفا صبر کنید...
    python -m venv .venv
    if errorlevel 1 (
        echo ساخت محیط برنامه با خطا مواجه شد.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 (
        echo نصب بسته‌های مورد نیاز با خطا مواجه شد. اتصال اینترنت را بررسی کنید.
        pause
        exit /b 1
    )
) else (
    call .venv\Scripts\activate.bat
)

if not exist "config.yaml" (
    copy config.example.yaml config.yaml >nul
    echo فایل تنظیمات ساخته شد: config.yaml
    echo پنجره‌ی Notepad باز می‌شود؛ آدرس دوربین را ویرایش کنید، ذخیره کنید و ببندید تا برنامه ادامه پیدا کند.
    pause
    notepad config.yaml
)

python run.py
if errorlevel 1 (
    echo برنامه با خطا متوقف شد. پیام بالا را برای رفع مشکل بررسی کنید.
    pause
)
