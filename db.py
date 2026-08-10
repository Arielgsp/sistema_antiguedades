"""
db.py - Capa de acceso a datos del Sistema de Antigüedad y Ascensos.

Garantías de robustez:
  * PRAGMA foreign_keys=ON siempre.
  * journal_mode=DELETE (el modo clásico de SQLite: bloquea el archivo
    completo durante cada escritura). Se eligió a propósito en vez de
    WAL porque WAL depende de archivos auxiliares con memoria
    compartida que NO funcionan de forma confiable en carpetas de red
    (SMB/Windows) -- si este programa se usa desde una carpeta
    compartida por varias PCs, DELETE es el modo que SQLite recomienda.
  * busy_timeout=15000 (15 segundos): si dos personas guardan casi al
    mismo tiempo, la segunda espera en silencio a que la primera
    termine, en vez de fallar o arriesgar el archivo. Con uso
    ocasional simultáneo (no constante) esto es suficiente.
  * synchronous=FULL (cada commit se asegura en disco antes de continuar).
  * Backup automático del archivo .db ANTES de cualquier operación de
    escritura invocada desde cli.py (ver backup_antes_de_escribir()).
  * Toda función de escritura corre dentro de una transacción explícita:
    si algo falla, se hace ROLLBACK completo (no quedan cambios "a medias").
  * Cada escritura registra una fila en `auditoria` con el valor anterior
    y el nuevo, dentro de LA MISMA transacción (o se guarda todo o nada).
"""

import sqlite3
import json
import shutil
import os
from datetime import datetime, date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = BASE_DIR / "backups"
DB_PATH = DATA_DIR / "antiguedad.db"

DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)


def get_connection():
    """Devuelve una conexión con las PRAGMA de robustez activadas."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = DELETE;")
    conn.execute("PRAGMA busy_timeout = 15000;")
    conn.execute("PRAGMA synchronous = FULL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea el esquema si no existe. Es seguro llamarla siempre al arrancar."""
    schema_path = BASE_DIR / "schema.sql"
    conn = get_connection()
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
    finally:
        conn.close()


def backup_antes_de_escribir(motivo="operacion"):
    """
    Copia el archivo .db completo a /backups con timestamp ANTES de
    cualquier operación de escritura relevante. Si algo sale mal durante
    la operación, siempre existe una copia intacta del estado anterior.
    No borra backups viejos (se acumulan; el usuario puede limpiarlos
    manualmente si hace falta, pero nunca se hace automáticamente para
    no arriesgar pérdida de datos).
    """
    if not DB_PATH.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = BACKUP_DIR / f"antiguedad_{ts}_{motivo}.db"
    shutil.copy2(DB_PATH, destino)
    return destino


def registrar_auditoria(conn, tabla, operacion, registro_id, valor_anterior, valor_nuevo, usuario):
    """Inserta una fila de auditoría DENTRO de la transacción activa de `conn`."""
    conn.execute(
        """INSERT INTO auditoria (tabla, operacion, registro_id, valor_anterior, valor_nuevo, usuario)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            tabla,
            operacion,
            str(registro_id),
            json.dumps(valor_anterior, ensure_ascii=False, default=str) if valor_anterior is not None else None,
            json.dumps(valor_nuevo, ensure_ascii=False, default=str) if valor_nuevo is not None else None,
            usuario,
        ),
    )


def row_to_dict(row):
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


class Transaccion:
    """
    Context manager para operaciones de escritura seguras:
      - hace backup del .db antes de empezar
      - abre conexión con BEGIN IMMEDIATE (evita condiciones de carrera)
      - si el bloque `with` termina sin excepción -> COMMIT
      - si hay cualquier excepción -> ROLLBACK total y se re-lanza el error
    Uso:
        with Transaccion("cargar_periodo") as conn:
            conn.execute(...)
            registrar_auditoria(conn, ...)
    """

    def __init__(self, motivo="operacion", hacer_backup=True):
        self.motivo = motivo
        self.hacer_backup = hacer_backup
        self.conn = None

    def __enter__(self):
        if self.hacer_backup:
            backup_antes_de_escribir(self.motivo)
        self.conn = get_connection()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            self.conn.close()
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                raise sqlite3.OperationalError(
                    "La base está siendo usada por otra persona en este momento. "
                    "Esperá unos segundos y probá de nuevo."
                ) from e
            raise
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()
        # No suprimimos la excepción: si algo falló, el usuario debe saberlo.
        return False


def verificar_integridad():
    """Corre PRAGMA integrity_check y devuelve (ok: bool, detalle: str)."""
    conn = get_connection()
    try:
        res = conn.execute("PRAGMA integrity_check;").fetchall()
        detalle = "; ".join(r[0] for r in res)
        ok = len(res) == 1 and res[0][0] == "ok"
        return ok, detalle
    finally:
        conn.close()
