@echo off
rem Privacy Guardian - one-click start (double-click this file).
rem Colab mode: backend + frontend + quick tunnel; opens the frontend in the
rem browser, copies the tunnel URL to the clipboard, and opens the Colab
rem notebook. Press Ctrl+C here to stop everything.
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Privacy Guardian - one-click start
echo   mode: Colab (tunnel + no local Ollama)   ports: backend 8000 /
echo   frontend 5173   press Ctrl+C to stop.
echo ============================================================
echo.

call dev.cmd --tunnel --colab-only --open-browser --copy-tunnel --open-colab %*
if errorlevel 1 (
  echo.
  echo [start] Privacy Guardian exited with an error. See logs above.
)

echo.
echo [start] Stopped. You can close this window.
pause
endlocal