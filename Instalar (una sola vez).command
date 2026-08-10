#!/bin/bash
cd "$(dirname "$0")"
echo "============================================================"
echo " Instalando lo necesario para que funcione el sistema..."
echo " (esto se hace UNA SOLA VEZ)"
echo "============================================================"
echo
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
echo
if [ $? -ne 0 ]; then
    echo "============================================================"
    echo " Hubo un problema durante la instalacion."
    echo " Verifique que Python 3 este instalado (python.org/downloads)."
    echo "============================================================"
else
    echo "============================================================"
    echo " Listo! Ya podes cerrar esta ventana y usar"
    echo " 'Iniciar Sistema.command' cada vez que quieras abrir el programa."
    echo "============================================================"
fi
echo
read -p "Presione Enter para cerrar..."
