"""
restaurar_csv.py - Reconstruye la base de datos completa a partir de una
carpeta de respaldo CSV generada por `python exportar.py backup_csv`.

Pensado para el peor caso: se perdió `data/antiguedad.db` Y todos los
archivos de `/backups`, y sólo queda un backup CSV (por ejemplo, una
copia guardada en otro lugar: email, pendrive, nube).

Por seguridad:
  - Si el archivo de destino ya existe y tiene agentes cargados, el
    script se niega a tocarlo (para no pisar una base buena por error).
    Usar --forzar sólo si estás seguro de que hay que reemplazarla.
  - Si el archivo de destino ya existe, antes de tocarlo se copia a
    /backups (igual que el resto del sistema).
  - Todo se inserta dentro de UNA transacción: si algo falla a mitad de
    camino, no queda nada a medias (rollback total).
  - Al final corre `PRAGMA integrity_check` y muestra un resumen de
    cuántas filas se restauraron por tabla.
  - Queda una fila en `auditoria` dejando constancia de la restauración
    (de qué carpeta, cuándo, quién la ejecutó).

Limitación conocida: el formato CSV no distingue un campo vacío ('') de
un campo NULL. Acá se trata cualquier valor vacío como NULL, que es el
comportamiento correcto para prácticamente todos los campos de este
sistema (fechas opcionales, observaciones, etc.).

Uso:
    python restaurar_csv.py exports/backup_csv_20260805_205423
    python restaurar_csv.py exports/backup_csv_20260805_205423 --forzar
    python restaurar_csv.py exports/backup_csv_20260805_205423 --destino otra_base.db
"""
import argparse
import csv
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from db import BASE_DIR, BACKUP_DIR, DB_PATH

TABLAS_EN_ORDEN = ["agentes", "periodos_antiguedad", "config_agente", "titulos",
                   "calculos_ascenso", "auditoria", "metadata"]


def _valor(v):
    """CSV no distingue '' de NULL; se trata todo string vacío como NULL."""
    return v if v not in (None, "") else None


def _leer_csv(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _integrity_check(conn):
    res = conn.execute("PRAGMA integrity_check;").fetchall()
    detalle = "; ".join(r[0] for r in res)
    ok = len(res) == 1 and res[0][0] == "ok"
    return ok, detalle


def restaurar_desde_csv(carpeta: str, usuario: str, destino: str = None, forzar: bool = False):
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise ValueError(f"No existe la carpeta {carpeta}")

    destino_path = Path(destino) if destino else DB_PATH
    destino_path.parent.mkdir(parents=True, exist_ok=True)

    # Importante: hay que decidir esto ANTES de abrir la conexión, porque
    # sqlite3.connect() crea el archivo en el momento de conectar aunque
    # todavía no se haya escrito nada (si no, esta comprobación siempre
    # vería el archivo como "ya existente", aunque no existiera antes).
    destino_ya_existia = destino_path.exists()
    if destino_ya_existia:
        BACKUP_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_destino = BACKUP_DIR / f"{destino_path.stem}_{ts}_antes_de_restaurar_csv.db"
        shutil.copy2(destino_path, backup_destino)
        print(f"Backup del archivo existente guardado en: {backup_destino}")

    conn = sqlite3.connect(destino_path)
    conn.row_factory = sqlite3.Row

    tablas_existentes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "agentes" in tablas_existentes:
        ya_hay_datos = conn.execute("SELECT COUNT(*) c FROM agentes").fetchone()[0] > 0
        if ya_hay_datos and not forzar:
            conn.close()
            raise RuntimeError(
                f"'{destino_path}' ya tiene agentes cargados. Para no arriesgar pisar "
                "datos buenos, este script no continúa. Si estás seguro de que hay que "
                "reemplazarla, volvé a correr con --forzar (igual se hace un backup antes)."
            )

    # Crea el esquema si hace falta, con la misma fuente que usa el resto del sistema.
    schema_path = BASE_DIR / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    # FK apagadas sólo durante el reemplazo: al reescribir tabla por tabla en
    # orden (agentes primero), borrar agentes con hijos viejos todavía cargados
    # violaría la FK si estuviera prendida. Se reactiva antes de terminar.
    conn.execute("PRAGMA foreign_keys = OFF;")
    resumen = {}
    try:
        conn.execute("BEGIN IMMEDIATE")
        for tabla in TABLAS_EN_ORDEN:
            conn.execute(f"DELETE FROM {tabla}")
            csv_path = carpeta / f"{tabla}.csv"
            if not csv_path.exists():
                resumen[tabla] = 0
                continue
            filas = _leer_csv(csv_path)
            if not filas:
                resumen[tabla] = 0
                continue
            columnas_tabla = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabla})")}
            columnas_csv = [c for c in filas[0].keys() if c in columnas_tabla]
            placeholders = ", ".join("?" for _ in columnas_csv)
            sql = f"INSERT INTO {tabla} ({', '.join(columnas_csv)}) VALUES ({placeholders})"
            for fila in filas:
                conn.execute(sql, [_valor(fila[c]) for c in columnas_csv])
            resumen[tabla] = len(filas)

        conn.execute(
            """INSERT INTO auditoria (tabla, operacion, registro_id, valor_nuevo, usuario)
               VALUES ('sistema', 'RESTORE_CSV', ?, ?, ?)""",
            (str(carpeta), json.dumps(resumen, ensure_ascii=False), usuario),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    conn.execute("PRAGMA foreign_keys = ON;")
    ok, detalle = _integrity_check(conn)
    conn.close()

    print("\nRestauración completa. Filas por tabla:")
    for tabla, cant in resumen.items():
        print(f"  {tabla}: {cant}")
    print(f"\nIntegridad de la base restaurada: {'OK' if ok else 'FALLÓ - ' + detalle}")
    if not ok:
        raise RuntimeError(f"La base restaurada no pasó integrity_check: {detalle}")
    return resumen


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Restaura la base de datos completa desde una carpeta de backup CSV.")
    parser.add_argument("carpeta", help="Carpeta con los .csv (ej: exports/backup_csv_AAAAMMDD_HHMMSS)")
    parser.add_argument("--usuario", default="restaurar_csv", help="Nombre de quien ejecuta la restauración")
    parser.add_argument("--destino", default=None,
                         help="Ruta del .db a crear/reemplazar (por defecto: data/antiguedad.db)")
    parser.add_argument("--forzar", action="store_true",
                         help="Reemplazar aunque el destino ya tenga datos cargados")
    args = parser.parse_args()
    restaurar_desde_csv(args.carpeta, args.usuario, destino=args.destino, forzar=args.forzar)
