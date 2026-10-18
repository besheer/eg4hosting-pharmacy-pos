@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3.12 -m venv .venv-win
if errorlevel 1 goto failed
goto install
:use_python
python -m venv .venv-win
if errorlevel 1 goto failed
:install
.venv-win\Scripts\python.exe -m pip install -r requirements-windows.txt
if errorlevel 1 goto failed
.venv-win\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --console --name eg4hosting-pharmacy-POS-v1.1.2 --paths . --hidden-import app.main --hidden-import app.pos_v05 --hidden-import app.catalog_reports --hidden-import app.ui --hidden-import app.pharmacy_brand --hidden-import openpyxl --collect-all uvicorn --add-data "app\pos.html;app" --add-data "data\egyptian-drugs.csv;data" windows\launcher.py
if errorlevel 1 goto failed
echo.
echo SUCCESS: dist\eg4hosting-pharmacy-POS-v1.1.2.exe
echo Copy this EXE to the Windows trial machine. Python and Docker are not needed there.
pause
exit /b 0
:failed
echo.
echo BUILD FAILED. Install Python 3.12 x64 from python.org and check the error above.
pause
exit /b 1
