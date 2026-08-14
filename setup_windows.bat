@echo off
setlocal
cd /d %~dp0

echo ==========================================
echo CwHUB CONFIG MARKETPLACE PRO - Windows

echo ==========================================

if exist .venv (
  echo Existing virtual environment found.
) else (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)

call .venv\Scripts\activate.bat
if errorlevel 1 goto :error

python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install --prefer-binary -r requirements.txt
if errorlevel 1 goto :error

if not exist .env copy .env.example .env >nul

python seed.py
if errorlevel 1 goto :error
python check_project.py
if errorlevel 1 goto :error

echo.
echo Setup complete.
echo Start with: python run.py
exit /b 0

:error
echo.
echo Setup failed. Read the error above.
exit /b 1
