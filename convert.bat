@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0vendor\libs\pypdf" (
  echo Packages are not installed yet. Running install.bat first...
  call "%~dp0install.bat" /nopause
  if not exist "%~dp0vendor\libs\pypdf" (
    echo Setup did not finish. Run install.bat, then try convert.bat again.
    pause
    exit /b 1
  )
)
python "%~dp0run.py"
pause
