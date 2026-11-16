@echo off
rem Builds dist\VassDash.exe. Run in Windows (double-click or Command Prompt).
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    set "DET_PYTHON=py -3"
) else (
    set "DET_PYTHON=python"
)
%DET_PYTHON% -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ required'"
if errorlevel 1 goto :failed
if not exist ".build_env\Scripts\python.exe" (
    %DET_PYTHON% -m venv .build_env
    if errorlevel 1 goto :failed
)
.build_env\Scripts\python.exe -m pip install "pyinstaller>=6,<7" -r requirements.txt
if errorlevel 1 goto :failed
.build_env\Scripts\python.exe -m compileall -q app.py det
if errorlevel 1 goto :failed
.build_env\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name "VassDash" --icon "assets\vassdash.ico" app.py
if errorlevel 1 goto :failed
echo.
echo Finished: dist\VassDash.exe
echo Copy that one file to each person. There is nothing to set up: it finds the team folder by itself.
explorer "%~dp0dist"
pause
exit /b 0
:failed
echo.
echo Build failed. Python 3.10+ and internet access for the build dependencies are required.
echo Review the error above.
pause
exit /b 1
