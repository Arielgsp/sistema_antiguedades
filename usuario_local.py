"""
usuario_local.py - Recuerda el nombre de quien usa el sistema EN ESTA PC
(no en la base de datos compartida, porque cada PC/persona puede ser
distinta).

Se guarda en la carpeta personal del usuario del sistema operativo
(Path.home()), NO al lado del programa -- a propósito, porque cuando el
programa vive en una carpeta de red compartida entre varias PCs, "al lado
del programa" deja de ser "esta PC" y pasa a ser un único archivo
compartido por todos: el primero que entra le terminaría poniendo su
nombre a todos los demás. Guardándolo en la carpeta personal de cada
usuario, cada PC (y cada usuario de Windows/Mac en esa PC) recuerda el
suyo, sin importar desde dónde se ejecute el programa.
"""
from pathlib import Path

ARCHIVO = Path.home() / ".sistema_antiguedad" / "usuario_local.txt"


def leer_usuario_guardado():
    if ARCHIVO.exists():
        nombre = ARCHIVO.read_text(encoding="utf-8").strip()
        return nombre or None
    return None


def guardar_usuario(nombre: str):
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(nombre.strip(), encoding="utf-8")
