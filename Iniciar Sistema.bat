@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw gui.py
) else (
    python gui.py
    if errorlevel 1 (
        echo.
        echo ============================================================
        echo  Hubo un problema al iniciar el sistema.
        echo  Verifique que ya ejecuto "Instalar (una sola vez).bat"
        echo  y que Python este instalado correctamente.
        echo ============================================================
        pause
    )
)
