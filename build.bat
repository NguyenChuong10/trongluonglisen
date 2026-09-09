@echo off
echo ===================================================
echo   DONG GOI JMS HELPER THANH FILE EXE TU DONG
echo ===================================================
echo.

:: Check pyinstaller
python -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo [Info] Dang cai dat pyinstaller va cac thu vien phu tro...
    pip install pyinstaller pywin32
)

echo [Info] Bat dau build file EXE bang PyInstaller...
python -m PyInstaller --clean --console --onefile --paths backend --add-data "frontend;frontend" --collect-all customtkinter --name "JMS_Helper" main.py

if %errorlevel% equ 0 (
    echo [Info] Dang di chuyen file EXE ra thu muc goc...
    move /Y dist\JMS_Helper.exe .
    rd /S /Q dist
    rd /S /Q build
    del /F /Q JMS_Helper.spec
    echo.
    echo ===================================================
    echo [Success] Dong goi thanh cong! 
    echo File chay: JMS_Helper.exe (nam ngay tai thu muc goc cua tool)
    echo ===================================================
) else (
    echo.
    echo [Error] Dong goi that bai! Vui long kiem tra log.
)
pause
