#!/bin/sh
set -e
cd "$(dirname "$0")"

echo
echo "EbaratNeshan setup"
echo "Installs Python packages into vendor/libs."
echo "On macOS/Linux, install Python 3.11+ yourself first (python.org or Homebrew)."
echo

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3.11+ was not found. Install it, then run this script again."
  echo "  macOS:  brew install python"
  echo "  Debian/Ubuntu:  sudo apt install python3 python3-pip python3-venv"
  exit 1
fi

"$PY" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" || {
  echo "EbaratNeshan needs Python 3.11 or newer."
  "$PY" --version
  exit 1
}

echo "Using: $PY"
"$PY" --version
mkdir -p vendor/libs

# Bundled wheels are Windows + CPython 3.13. Other systems download once.
if [ -d vendor/wheels ] && "$PY" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) and sys.platform == 'win32' else 1)"; then
  echo "Using local wheels (no download)."
  "$PY" -m pip install --disable-pip-version-check --no-index --find-links=vendor/wheels -r requirements.txt -t vendor/libs
else
  echo "Downloading packages with pip (needs internet once)."
  "$PY" -m pip install --disable-pip-version-check -r requirements.txt -t vendor/libs
fi

echo
echo "Setup finished. Run:  python3 run_web.py"
echo "Leave that terminal open. A page opens at http://127.0.0.1:8765/"
echo
