"""
migracion_datos_1421_v2.py - Corrige tres problemas detectados por el
usuario comparando contra el reporte original de Access:

  1. Faltaban períodos de antigüedad ANTERIORES al Ministerio (ej.
     pasantías, otros organismos) que están en la tabla `Nac_Priv` de
     Datos_Pers_2021.mdb. Se importan SOLO para los 198 agentes que
     cuentan bajo 1421 (el resto es irrelevante para este sistema).
     Se importan con cuenta_ascenso=0 por defecto (así es como Access
     los trata: no suman para el ascenso de grado 1421), pero SÍ quedan
     visibles y marcados con suma_apn=1/0 según corresponda (para poder
     mostrar el total de "Antigüedad en la Administración Pública
     Nacional", que es un número distinto al de ascenso de grado).

  2. El Nivel/Grado que se había importado (de Agentes_actual) no es el
     correcto para el régimen 1421 (esa tabla usa otra escala general).
     El Nivel/Grado real del contrato 1421/02 está en `Listado_1421`
     (archivo Contratados_1421_-_2345_-_PNUD__2026.mdb). Se corrige
     tomando el registro más reciente (por INICIO_1421) de cada agente.

  3. Se guardan además la dependencia y las fechas del contrato 1421
     vigente, para mostrarlas en la ficha.

Es idempotente y corre en una única transacción con backup previo.
"""
import csv
from datetime import datetime

from db import init_db, Transaccion, registrar_auditoria, get_connection, row_to_dict


def leer_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_fecha_access(valor):
    if not valor or not valor.strip():
        return None
    valor = valor.strip()
    for fmt in ["%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%m/%d/%y", "%m/%d/%Y"]:
        try:
            dt = datetime.strptime(valor, fmt)
            if dt.year > datetime.now().year + 5:
                dt = dt.replace(year=dt.year - 100)
            return dt.date().isoformat()
        except ValueError:
            continue
    return None


def asegurar_columnas(conn):
    cols_periodos = {r["name"] for r in conn.execute("PRAGMA table_info(periodos_antiguedad)")}
    agregados = []
    for col, tipo in [("tipo_prestacion", "TEXT"), ("suma_apn", "INTEGER NOT NULL DEFAULT 1"),
                       ("planta_nac", "TEXT"), ("motivo_baja", "TEXT")]:
        if col not in cols_periodos:
            conn.execute(f"ALTER TABLE periodos_antiguedad ADD COLUMN {col} {tipo}")
            agregados.append(f"periodos_antiguedad.{col}")

    cols_agentes = {r["name"] for r in conn.execute("PRAGMA table_info(agentes)")}
    for col, tipo in [("dependencia_1421", "TEXT"), ("contrato_desde_1421", "TEXT"),
                       ("contrato_hasta_1421", "TEXT")]:
        if col not in cols_agentes:
            conn.execute(f"ALTER TABLE agentes ADD COLUMN {col} {tipo}")
            agregados.append(f"agentes.{col}")
    return agregados


def migrar(nac_priv_csv, listado_1421_csv, usuario):
    init_db()
    resumen = {"columnas_agregadas": [], "periodos_nacpriv_insertados": 0,
               "periodos_nacpriv_omitidos_no_1421": 0, "agentes_nivel_grado_corregido": 0,
               "suma_apn_marcado_en_periodos_existentes": 0}

    with Transaccion("migracion_datos_1421_v2") as conn:
        resumen["columnas_agregadas"] = asegurar_columnas(conn)

        # docs que cuentan bajo 1421 (única población relevante)
        docs_1421 = {r["n_doc"] for r in conn.execute("SELECT n_doc FROM agentes WHERE cuenta_1421=1")}

        # ---- 1) marcar suma_apn=1 en los períodos ya importados (Ministerio actual) ----
        periodos_existentes = conn.execute(
            "SELECT id, suma_apn FROM periodos_antiguedad WHERE origen='importado'").fetchall()
        for p in periodos_existentes:
            if p["suma_apn"] != 1:
                conn.execute("UPDATE periodos_antiguedad SET suma_apn=1 WHERE id=?", (p["id"],))
                resumen["suma_apn_marcado_en_periodos_existentes"] += 1

        # ---- 2) importar Nac_Priv (períodos anteriores), sólo para los 198 relevantes ----
        nac_priv_rows = leer_csv(nac_priv_csv)
        ya_importados = set()
        for r in nac_priv_rows:
            if not r.get("N_doc") or not r["N_doc"].strip().isdigit():
                continue
            n_doc = int(r["N_doc"])
            if n_doc not in docs_1421:
                resumen["periodos_nacpriv_omitidos_no_1421"] += 1
                continue

            fecha_desde = parse_fecha_access(r.get("Desde"))
            if not fecha_desde:
                continue
            fecha_hasta = parse_fecha_access(r.get("Hasta"))
            organismo = (r.get("Lugar") or "").strip()
            tipo_prestacion = (r.get("T_Pres") or "").strip()
            planta_nac = (r.get("Planta_Nac") or "").strip()
            motivo_baja = (r.get("Motivo_baja") or "").strip()
            suma_apn = 1 if (r.get("suma_ant") or "").strip() == "1" else 0

            clave = (n_doc, fecha_desde, fecha_hasta, organismo)
            if clave in ya_importados:
                continue
            ya_importados.add(clave)

            # evitar duplicar si ya existe un período idéntico (por si se corre 2 veces)
            existe = conn.execute(
                """SELECT id FROM periodos_antiguedad WHERE n_doc=? AND fecha_desde=?
                       AND IFNULL(fecha_hasta,'')=IFNULL(?,'') AND organismo=? AND origen='importado_nac_priv'""",
                (n_doc, fecha_desde, fecha_hasta, organismo)).fetchone()
            if existe:
                continue

            cur = conn.execute(
                """INSERT INTO periodos_antiguedad
                       (n_doc, fecha_desde, fecha_hasta, organismo, cuenta_ascenso, observaciones,
                        origen, usuario_carga, tipo_prestacion, suma_apn, planta_nac, motivo_baja)
                   VALUES (?, ?, ?, ?, 0, ?, 'importado_nac_priv', ?, ?, ?, ?, ?)""",
                (n_doc, fecha_desde, fecha_hasta, organismo,
                 "Importado desde Nac_Priv (servicio anterior). No cuenta para ascenso de grado 1421 "
                 "por defecto -- revisar si corresponde otro criterio.",
                 usuario, tipo_prestacion, suma_apn, planta_nac, motivo_baja),
            )
            registrar_auditoria(conn, "periodos_antiguedad", "INSERT", cur.lastrowid, None,
                                 {"n_doc": n_doc, "fecha_desde": fecha_desde, "organismo": organismo,
                                  "origen": "importado_nac_priv"}, usuario)
            resumen["periodos_nacpriv_insertados"] += 1

        # ---- 3) corregir Nivel/Grado real (desde Listado_1421, el más reciente por INICIO_1421) ----
        listado_rows = leer_csv(listado_1421_csv)
        mejor_por_doc = {}
        for r in listado_rows:
            if not r.get("doc_1421") or not r["doc_1421"].strip().isdigit():
                continue
            n_doc = int(r["doc_1421"])
            inicio = parse_fecha_access(r.get("INICIO_1421")) or ""
            actual = mejor_por_doc.get(n_doc)
            if actual is None or inicio > actual["inicio"]:
                mejor_por_doc[n_doc] = {
                    "inicio": inicio,
                    "nivel": (r.get("NIVEL") or "").strip() or None,
                    "grado": (r.get("GRADO") or "").strip() or None,
                    "dependencia": (r.get("DEPENDENCIA") or "").strip() or None,
                    "fin": parse_fecha_access(r.get("FIN_1421")),
                }

        for n_doc in docs_1421:
            datos = mejor_por_doc.get(n_doc)
            if not datos:
                continue
            anterior = conn.execute(
                "SELECT nivel_actual, grado_actual, dependencia_1421, contrato_desde_1421, contrato_hasta_1421 "
                "FROM agentes WHERE n_doc=?", (n_doc,)).fetchone()
            anterior = row_to_dict(anterior)
            grado_int = int(datos["grado"]) if datos["grado"] and datos["grado"].isdigit() else None
            nuevo = {"nivel_actual": datos["nivel"], "grado_actual": grado_int,
                     "dependencia_1421": datos["dependencia"], "contrato_desde_1421": datos["inicio"] or None,
                     "contrato_hasta_1421": datos["fin"]}
            if anterior != nuevo:
                conn.execute(
                    """UPDATE agentes SET nivel_actual=?, grado_actual=?, dependencia_1421=?,
                           contrato_desde_1421=?, contrato_hasta_1421=?, fecha_modif=?, usuario_modif=?
                       WHERE n_doc=?""",
                    (nuevo["nivel_actual"], nuevo["grado_actual"], nuevo["dependencia_1421"],
                     nuevo["contrato_desde_1421"], nuevo["contrato_hasta_1421"],
                     datetime.now().isoformat(), usuario, n_doc),
                )
                registrar_auditoria(conn, "agentes", "UPDATE", n_doc, anterior, nuevo, usuario)
                resumen["agentes_nivel_grado_corregido"] += 1

        conn.execute(
            "INSERT OR REPLACE INTO metadata (clave, valor) VALUES ('migracion_datos_1421_v2_fecha', ?)",
            (datetime.now().isoformat(),),
        )

    return resumen


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("nac_priv_csv")
    ap.add_argument("listado_1421_csv")
    ap.add_argument("--usuario", default="migracion_datos_1421_v2")
    args = ap.parse_args()
    r = migrar(args.nac_priv_csv, args.listado_1421_csv, args.usuario)
    print("Resumen:")
    for k, v in r.items():
        print(f"  {k}: {v}")
