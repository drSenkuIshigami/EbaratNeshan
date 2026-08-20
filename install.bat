@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
chcp 65001 >nul

set "PAUSE_AT_END=1"
if /I "%~1"=="/nopause" set "PAUSE_AT_END=0"

echo.
echo  EbaratNeshan setup
echo  This installs Python if needed, then the packages EbaratNeshan uses.
echo  Files stay on this computer. A browser window to python.org only
echo  opens if Windows cannot install Python automatically.
echo.

call :find_python
if not defined PYTHON goto :need_python

call :check_version
if errorlevel 1 goto :need_python

echo Using: %PYTHON%
"%PYTHON%" --version
echo.

call :install_packages
if errorlevel 1 (
  echo.
  echo Setup did not finish. See the messages above.
  pause
  exit /b 1
)

echo.
echo Setup finished. You can double-click web.bat to open the local page.
echo Keep that window open while you convert files.
echo.
if "%PAUSE_AT_END%"=="1" pause
exit /b 0

:need_python
echo Python 3.11 or newer was not found.
echo Trying to install Python 3.13 with winget...
where winget >nul 2>&1
if errorlevel 1 goto :manual_python

winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo winget could not install Python.
  goto :manual_python
)

set "PATH=%LocalAppData%\Programs\Python\Python313;%LocalAppData%\Programs\Python\Python313\Scripts;%PATH%"
call :find_python
if not defined PYTHON goto :manual_python
call :check_version
if errorlevel 1 goto :manual_python

echo Using: %PYTHON%
"%PYTHON%" --version
echo.
call :install_packages
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo Setup finished. You can double-click web.bat
if "%PAUSE_AT_END%"=="1" pause
exit /b 0

:manual_python
echo.
echo Please install Python 3.11 or newer from:
echo   https://www.python.org/downloads/windows/
echo Check "Add python.exe to PATH", then run this file again.
echo.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:find_python
set "PYTHON="
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYTHON=%LocalAppData%\Programs\Python\Python313\python.exe"
if defined PYTHON goto :eof
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"
if defined PYTHON goto :eof
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    set "PYTHON=py"
    set "PYARGS=-3"
    goto :eof
  )
)
where python >nul 2>&1
if not errorlevel 1 set "PYTHON=python"
if defined PYTHON goto :eof
where python3 >nul 2>&1
if not errorlevel 1 set "PYTHON=python3"
goto :eof

:check_version
if /I "%PYTHON%"=="py" (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
  exit /b %ERRORLEVEL%
)
"%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
exit /b %ERRORLEVEL%

:install_packages
echo Installing packages into vendor\libs ...
if not exist "%~dp0vendor\libs" mkdir "%~dp0vendor\libs"

if /I "%PYTHON%"=="py" (
  set "PYCMD=py -3"
) else (
  set "PYCMD="%PYTHON%""
)

set "WHEELS=%~dp0vendor\wheels"
set "USE_WHEELS=0"
if exist "%WHEELS%\pypdf-6.15.0-py3-none-any.whl" set "USE_WHEELS=1"

if "%USE_WHEELS%"=="1" (
  if /I "%PYTHON%"=="py" (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) and sys.platform == 'win32' else 1)"
  ) else (
    "%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) and sys.platform == 'win32' else 1)"
  )
  if not errorlevel 1 (
    echo Using local wheels in vendor\wheels  ^(Windows, Python 3.13, no download^)
    if /I "%PYTHON%"=="py" (
      py -3 -m pip install --disable-pip-version-check --no-index --find-links="%~dp0vendor\wheels" -r "%~dp0requirements.txt" -t "%~dp0vendor\libs"
    ) else (
      "%PYTHON%" -m pip install --disable-pip-version-check --no-index --find-links="%~dp0vendor\wheels" -r "%~dp0requirements.txt" -t "%~dp0vendor\libs"
    )
    exit /b %ERRORLEVEL%
  )
)

echo Local wheels do not match this Python. Downloading packages with pip ^(needs internet once^).
if /I "%PYTHON%"=="py" (
  py -3 -m pip install --disable-pip-version-check -r "%~dp0requirements.txt" -t "%~dp0vendor\libs"
) else (
  "%PYTHON%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt" -t "%~dp0vendor\libs"
)
exit /b %ERRORLEVEL%
