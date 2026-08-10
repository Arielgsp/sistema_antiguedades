@echo off
title Instalando el Sistema de Antiguedad
cd /d "%~dp0"
echo ============================================================
echo  Instalando lo necesario para que funcione el sistema...
echo  (esto se hace UNA SOLA VEZ)
echo ============================================================
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
if errorlevel 1 (
    echo ============================================================
    echo  Hubo un problema durante la instalacion.
    echo  Verifique que Python este instalado y que al instalarlo
    echo  haya tildado la casilla "Add python.exe to PATH".
    echo ============================================================
) else (
    echo ============================================================
    echo  Listo! Ya podes cerrar esta ventana y usar
    echo  "Iniciar Sistema.bat" cada vez que quieras abrir el programa.
    echo ============================================================
)
echo.
pause
