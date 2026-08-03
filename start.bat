@echo off
REM Windows: shu faylga ikki marta bosing.
REM Python'ni topib, start.py ga hamma ishni topshiradi.

cd /d "%~dp0"

REM `py` — Windows'ning python topuvchisi, PATH sozlanmagan bo'lsa ham ishlaydi.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 start.py %*
    goto done
)

where python >nul 2>nul
if %errorlevel%==0 (
    python start.py %*
    goto done
)

echo.
echo  [!] Python topilmadi.
echo.
echo  1. https://www.python.org/downloads/ dan yuklab oling
echo  2. O'rnatishda "Add python.exe to PATH" katagini BELGILANG
echo  3. Kompyuterni qaytadan yoqing va shu faylni yana ishga tushiring
echo.
pause
exit /b 1

:done
REM Server to'xtaganda oyna darhol yopilmasin.
if %errorlevel% neq 0 pause
