#!/bin/bash
cd "$(dirname "$0")"
python3 gui.py
if [ $? -ne 0 ]; then
    echo
    echo "============================================================"
    echo " Hubo un problema al iniciar el sistema."
    echo " Verifique que ya ejecuto 'Instalar (una sola vez).command'"
    echo "============================================================"
    read -p "Presione Enter para cerrar..."
fi
