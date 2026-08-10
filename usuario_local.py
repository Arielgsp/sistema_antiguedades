"""
usuario_local.py - Recuerda el nombre de quien usa el sistema EN ESTA PC
(no en la base de datos compartida, porque cada PC/persona puede ser
distinta). Se guarda en un archivo de texto simple junto al programa.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ARCHIVO = BASE_DIR / "data" / "usuario_local.txt"


def leer_usuario_guardado():
    if ARCHIVO.exists():
        nombre = ARCHIVO.read_text(encoding="utf-8").strip()
        return nombre or None
    return None


def guardar_usuario(nombre: str):
    ARCHIVO.parent.mkdir(exist_ok=True)
    ARCHIVO.write_text(nombre.strip(), encoding="utf-8")
