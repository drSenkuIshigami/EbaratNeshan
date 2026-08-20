@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0vendor\libs\pypdf" (
  echo Packages are not installed yet. Running install.bat first...
  call "%~dp0install.bat" /nopause
  if not exist "%~dp0vendor\libs\pypdf" (
    echo Setup did not finish. Run install.bat, then try web.bat again.
    pause
    exit /b 1
  )
)
echo Opening EbaratNeshan in your browser. Leave this window open.
python -u "%~dp0run_web.py"
if errorlevel 1 (
  echo.
  echo If Python was not found, run install.bat once, then try again.
)
pause
