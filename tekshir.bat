@echo off
REM QR ishlamayotgan bo'lsa — shu faylga ikki marta bosing.
REM QR ichida aynan qanday havola borligini ko'rsatadi.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  [!] Tizim hali o'rnatilmagan.
    echo      Avval start.bat ni bir marta ishga tushiring.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" manage.py qr-check

echo.
pause
