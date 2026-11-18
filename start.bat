@echo off
setlocal
cd /d "%~dp0"
title Hassan

if exist ".venv\Scripts\python.exe" goto run
echo First run: setting up Hassan (this takes a minute)...
set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE (
  echo Python is not installed. Installing Python 3.12 from Microsoft's package manager...
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PYEXE (
  echo.
  echo Could not install Python automatically. Install it from python.org, then run start.bat again.
  pause
  exit /b 1
)
if "%PYEXE%"=="py -3" (py -3 -m venv .venv) else ("%PYEXE%" -m venv .venv)
if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python environment failed.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
  echo Installing the Python packages failed. Check your internet connection.
  if exist ".venv" rmdir /s /q ".venv"
  pause
  exit /b 1
)

:run
if not exist ".env" copy ".env.example" ".env" >nul
where claude >nul 2>nul
if errorlevel 1 echo WARNING: Claude Code ("claude") was not found on your PATH. Hassan needs it.
set OPEN_BROWSER=1
echo Starting Hassan on http://localhost:8340  (close this window to stop him)
".venv\Scripts\python.exe" server.py
pause
