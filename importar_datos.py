"""
importar_datos.py - Carga inicial (una sola vez) de los datos existentes
en Datos_Pers_2021.mdb hacia la base robusta del sistema.

Toda la importación corre en UNA transacción: si algo falla a mitad de
camino, no queda nada cargado a medias (rollback total).

Uso:
    python importar_datos.py /ruta/a/Agentes_actual.csv /ruta/a/Antiguedad_LO.csv \
        /ruta/a/Agente_titulo.csv [--usuario "Ariel"]
"""

import csv
import sys
import argparse
from datetime import datetime, date

from db import init_db, Transaccion, registrar_auditoria, get_connection


def parse_fecha_access(valor):
    """Convierte 'MM/DD/YY HH:MM:SS' (formato de mdb-export) a 'YYYY-MM-DD'."""
    if not valor or not valor.strip():
        return None
    valor = valor.strip()
    formatos = ["%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%m/%d/%y", "%m/%d/%Y"]
    for fmt in formatos:
        try:
            dt = datetime.strptime(valor, fmt)
            # Corrección de siglo: mdb-tools interpreta años de 2 dígitos
            # con pivote en 68/69; si da una fecha futura absurda, restar 100 años.
            if dt.year > datetime.now().year + 5:
                dt = dt.replace(year=dt.year - 100)
            return dt.date().isoformat()
        except ValueError:
            continue
    return None


def leer_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def importar(agentes_csv, antiguedad_csv, titulos_csv, usuario="importacion_inicial"):
    init_db()

    agentes_rows = leer_csv(agentes_csv)
    antig_rows = leer_csv(antiguedad_csv)
    titulos_rows = leer_csv(titulos_csv)

    resumen = {
        "agentes_insertados": 0,
        "agentes_omitidos_ya_existian": 0,
        "periodos_insertados": 0,
        "periodos_omitidos_sin_fecha": 0,
        "titulos_insertados": 0,
        "errores": [],
    }

    with Transaccion("importacion_inicial") as conn:
        # ---- 1) AGENTES ----
        existentes = {r["n_doc"] for r in conn.execute("SELECT n_doc FROM agentes")}
        for r in agentes_rows:
            try:
                n_doc = int(r["N_doc"])
            except (ValueError, TypeError, KeyError):
                continue
            if n_doc in existentes:
                resumen["agentes_omitidos_ya_existian"] += 1
                continue
            nombre = (r.get("Agente") or "").strip() or f"SIN NOMBRE ({n_doc})"
            nivel = (r.get("Niv") or "").strip() or None
            grado_raw = (r.get("gra") or "").strip()
            grado = int(grado_raw) if grado_raw.isdigit() else None

            conn.execute(
                """INSERT INTO agentes (n_doc, apellido_nombre, nivel_actual, grado_actual, origen, usuario_modif)
                   VALUES (?, ?, ?, ?, 'importado', ?)""",
                (n_doc, nombre, nivel, grado, usuario),
            )
            registrar_auditoria(conn, "agentes", "INSERT", n_doc, None,
                                 {"n_doc": n_doc, "apellido_nombre": nombre,
                                  "nivel_actual": nivel, "grado_actual": grado},
                                 usuario)
            existentes.add(n_doc)
            resumen["agentes_insertados"] += 1

            # config_agente por defecto (vacía, se completa manualmente después)
            conn.execute(
                "INSERT OR IGNORE INTO config_agente (n_doc, usuario_modif) VALUES (?, ?)",
                (n_doc, usuario),
            )

        # ---- 2) PERIODOS DE ANTIGÜEDAD (desde Antiguedad_LO) ----
        # Antiguedad_LO trae F_alta = fecha desde la que se computa la
        # antigüedad de ese agente (según el sistema legado). Se importa
        # como UN período abierto (fecha_hasta=NULL) marcado cuenta_ascenso=1
        # por defecto -- el usuario puede después dividirlo, cerrarlo o
        # desmarcarlo según corresponda.
        vistos_periodo = set()  # evita duplicar filas idénticas repetidas en el export
        for r in antig_rows:
            try:
                n_doc = int(r["N_doc"])
            except (ValueError, TypeError, KeyError):
                continue
            if n_doc not in existentes:
                # el agente no está en Agentes_actual (puede ser una baja);
                # lo damos de alta igual para no perder el dato de antigüedad,
                # marcado como inactivo.
                nombre = (r.get("Agente") or f"SIN NOMBRE ({n_doc})").strip()
                conn.execute(
                    """INSERT INTO agentes (n_doc, apellido_nombre, activo, origen, usuario_modif)
                       VALUES (?, ?, 0, 'importado', ?)""",
                    (n_doc, nombre, usuario),
                )
                registrar_auditoria(conn, "agentes", "INSERT", n_doc, None,
                                     {"n_doc": n_doc, "apellido_nombre": nombre, "activo": 0},
                                     usuario)
                conn.execute(
                    "INSERT OR IGNORE INTO config_agente (n_doc, usuario_modif) VALUES (?, ?)",
                    (n_doc, usuario),
                )
                existentes.add(n_doc)
                resumen["agentes_insertados"] += 1

            fecha_desde = parse_fecha_access(r.get("F_alta"))
            if not fecha_desde:
                resumen["periodos_omitidos_sin_fecha"] += 1
                continue

            organismo = (r.get("Total_LO_frac_Sectores") or "").strip()
            clave = (n_doc, fecha_desde, organismo)
            if clave in vistos_periodo:
                continue  # fila duplicada exacta en el export original
            vistos_periodo.add(clave)

            cur = conn.execute(
                """INSERT INTO periodos_antiguedad
                       (n_doc, fecha_desde, fecha_hasta, organismo, cuenta_ascenso,
                        observaciones, origen, usuario_carga)
                   VALUES (?, ?, NULL, ?, 1, ?, 'importado', ?)""",
                (n_doc, fecha_desde, organismo,
                 "Importado desde Antiguedad_LO (Datos_Pers_2021.mdb)", usuario),
            )
            registrar_auditoria(conn, "periodos_antiguedad", "INSERT", cur.lastrowid, None,
                                 {"n_doc": n_doc, "fecha_desde": fecha_desde,
                                  "organismo": organismo, "cuenta_ascenso": 1},
                                 usuario)
            resumen["periodos_insertados"] += 1

        # ---- 3) TÍTULOS ----
        for r in titulos_rows:
            try:
                n_doc = int(r["N_doc"])
            except (ValueError, TypeError, KeyError):
                continue
            if n_doc not in existentes:
                continue  # no se crean agentes nuevos sólo por un título suelto

            id_niv = (r.get("Id_niv") or "").strip() or None
            titulo = (r.get("id_tit") or "").strip() or None
            institucion = (r.get("Institucion") or "").strip() or None
            fecha_egreso = parse_fecha_access(r.get("Fecha_egreso"))
            fecha_titulacion = parse_fecha_access(r.get("Fecha_Titulacion"))
            es_grado = 1 if id_niv == "U" else 0

            if not any([titulo, fecha_titulacion, institucion]):
                continue  # fila vacía, no aporta información

            cur = conn.execute(
                """INSERT INTO titulos
                       (n_doc, id_niv, titulo, institucion, fecha_egreso,
                        fecha_titulacion, es_titulo_grado, origen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'importado')""",
                (n_doc, id_niv, titulo, institucion, fecha_egreso, fecha_titulacion, es_grado),
            )
            registrar_auditoria(conn, "titulos", "INSERT", cur.lastrowid, None,
                                 {"n_doc": n_doc, "titulo": titulo, "id_niv": id_niv,
                                  "fecha_titulacion": fecha_titulacion, "es_titulo_grado": es_grado},
                                 usuario)
            resumen["titulos_insertados"] += 1

        conn.execute(
            "INSERT OR REPLACE INTO metadata (clave, valor) VALUES ('importacion_inicial_fecha', ?)",
            (datetime.now().isoformat(),),
        )

    return resumen


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Importación inicial del sistema de antigüedad")
    ap.add_argument("agentes_csv")
    ap.add_argument("antiguedad_csv")
    ap.add_argument("titulos_csv")
    ap.add_argument("--usuario", default="importacion_inicial")
    args = ap.parse_args()

    resumen = importar(args.agentes_csv, args.antiguedad_csv, args.titulos_csv, args.usuario)
    print("Resumen de importación:")
    for k, v in resumen.items():
        print(f"  {k}: {v}")
