@echo off
rem Privacy Guardian - one-command launcher.
rem Auto-setup (uv sync / npm install if missing), then backend + frontend.
rem Usage: dev.cmd [--tunnel] [--colab-only] [--no-frontend] [--no-backend] [--port N]
setlocal
cd /d "%~dp0"

if not exist ".venv" (
  echo [setup] creating Python env ^(uv sync^)...
  call uv sync
  if errorlevel 1 exit /b 1
)

if not exist "app\frontend\node_modules" (
  echo [setup] installing frontend deps ^(npm install^)...
  pushd app\frontend
  call npm install
  popd
  if errorlevel 1 exit /b 1
)

call uv run python scripts/dev.py %*
endlocal
