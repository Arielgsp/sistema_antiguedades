"""
migracion_agentes_faltantes.py - Agrega al sistema los agentes que están
en el universo real del Decreto 1421/02 (Listado_1421 + relacionadas,
sin fecha de baja en CONTRATADOS) pero que no habían entrado al sistema
porque no figuraban en Agentes_actual/Antiguedad_LO (típicamente altas
muy recientes, 2025/2026, que ese sistema legado todavía no había
procesado).

Fuentes usadas para cada agente nuevo:
  - Nombre: DPersonales (Apellido + Nombre) o, si falta, CONTRATADOS.
  - Nivel/Grado/Dependencia/Contrato: Listado_1421 (registro más reciente).
  - Período de antigüedad actual: Antiguedad_LO si existe; si no, se usa
    DPersonales.fecha_ing (fecha de ingreso) como fecha_desde de un
    período "vigente" que cuenta para el ascenso de grado.
  - Períodos anteriores: Nac_Priv (igual que para el resto del sistema).
  - Títulos: Agente_titulo.

Es idempotente: si el agente ya existe, no lo duplica.
"""
import csv
from datetime import datetime

from db import init_db, Transaccion, registrar_auditoria, get_connection


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


def docs_de(rows, col):
    s = set()
    for r in rows:
        v = r.get(col)
        if v and v.strip().isdigit():
            s.add(int(v))
    return s


def migrar(contratados_csv, listado_1421_csv, historico_csv, nivel_csv, asu_csv,
           dpersonales_csv, antig_lo_csv, nac_priv_csv, agente_titulo_csv, usuario):
    init_db()
    resumen = {"agentes_nuevos": 0, "periodos_actuales_agregados": 0,
               "periodos_actuales_por_fecha_ingreso": 0, "periodos_nacpriv_agregados": 0,
               "titulos_agregados": 0}

    contratados = leer_csv(contratados_csv)
    con_baja = set(int(r["N_doc"]) for r in contratados
                    if r["N_doc"] and r["N_doc"].strip().isdigit()
                    and r.get("Fecha de baja") and r["Fecha de baja"].strip())
    nombre_contratados = {int(r["N_doc"]): r.get("Apellido y Nombre", "").strip()
                           for r in contratados if r["N_doc"] and r["N_doc"].strip().isdigit()}

    listado_rows = leer_csv(listado_1421_csv)
    union_1421 = (docs_de(listado_rows, "doc_1421")
                  | docs_de(leer_csv(historico_csv), "doc_1421")
                  | docs_de(leer_csv(nivel_csv), "Numero")
                  | docs_de(leer_csv(asu_csv), "NUMERO"))
    roster = union_1421 - con_baja

    # mejor registro de Listado_1421 por doc (más reciente por INICIO_1421)
    mejor_1421 = {}
    for r in listado_rows:
        if not r.get("doc_1421") or not r["doc_1421"].strip().isdigit():
            continue
        n_doc = int(r["doc_1421"])
        inicio = parse_fecha_access(r.get("INICIO_1421")) or ""
        actual = mejor_1421.get(n_doc)
        if actual is None or inicio > actual["inicio"]:
            mejor_1421[n_doc] = {
                "inicio": inicio, "nivel": (r.get("NIVEL") or "").strip() or None,
                "grado": (r.get("GRADO") or "").strip() or None,
                "dependencia": (r.get("DEPENDENCIA") or "").strip() or None,
                "fin": parse_fecha_access(r.get("FIN_1421")),
            }

    dpersonales = {int(r["N_doc"]): r for r in leer_csv(dpersonales_csv)
                   if r.get("N_doc") and r["N_doc"].strip().isdigit()}
    antig_lo = {}
    for r in leer_csv(antig_lo_csv):
        if r.get("N_doc") and r["N_doc"].strip().isdigit():
            antig_lo.setdefault(int(r["N_doc"]), r)  # primer registro si hay duplicados

    nac_priv_rows = leer_csv(nac_priv_csv)
    titulos_rows = leer_csv(agente_titulo_csv)

    with Transaccion("migracion_agentes_faltantes") as conn:
        existentes = {r["n_doc"] for r in conn.execute("SELECT n_doc FROM agentes")}

        for n_doc in sorted(roster):
            if n_doc in existentes:
                continue  # ya está en el sistema (de la importación original)

            dp = dpersonales.get(n_doc)
            if dp and (dp.get("Apellido") or dp.get("Nombre")):
                nombre = f"{dp.get('Apellido', '').strip()}, {dp.get('Nombre', '').strip()}"
            else:
                nombre = nombre_contratados.get(n_doc) or f"SIN NOMBRE ({n_doc})"

            datos_1421 = mejor_1421.get(n_doc, {})
            grado_int = None
            if datos_1421.get("grado") and datos_1421["grado"].isdigit():
                grado_int = int(datos_1421["grado"])

            conn.execute(
                """INSERT INTO agentes
                       (n_doc, apellido_nombre, nivel_actual, grado_actual, activo, origen,
                        usuario_modif, vinculado_1421, tiene_baja_1421, cuenta_1421,
                        motivo_clasif_1421, dependencia_1421, contrato_desde_1421, contrato_hasta_1421)
                   VALUES (?, ?, ?, ?, 1, 'importado_faltante', ?, 1, 0, 1,
                           'Vinculado a Decreto 1421/02 (agregado en corrección: no figuraba en Agentes_actual/Antiguedad_LO)',
                           ?, ?, ?)""",
                (n_doc, nombre, datos_1421.get("nivel"), grado_int, usuario,
                 datos_1421.get("dependencia"), datos_1421.get("inicio") or None, datos_1421.get("fin")),
            )
            registrar_auditoria(conn, "agentes", "INSERT", n_doc, None,
                                 {"n_doc": n_doc, "apellido_nombre": nombre, "origen": "importado_faltante"}, usuario)
            conn.execute("INSERT OR IGNORE INTO config_agente (n_doc, usuario_modif) VALUES (?, ?)", (n_doc, usuario))
            resumen["agentes_nuevos"] += 1

            # ---- período actual: Antiguedad_LO si existe, si no fecha_ing de DPersonales ----
            fila_antig = antig_lo.get(n_doc)
            fecha_desde_actual = None
            organismo_actual = ""
            if fila_antig:
                fecha_desde_actual = parse_fecha_access(fila_antig.get("F_alta"))
                organismo_actual = (fila_antig.get("Total_LO_frac_Sectores") or "").strip()
                resumen["periodos_actuales_agregados"] += 1
            elif dp and dp.get("fecha_ing"):
                fecha_desde_actual = parse_fecha_access(dp.get("fecha_ing"))
                organismo_actual = datos_1421.get("dependencia") or "Ministerio de Defensa"
                resumen["periodos_actuales_por_fecha_ingreso"] += 1

            if fecha_desde_actual:
                cur = conn.execute(
                    """INSERT INTO periodos_antiguedad
                           (n_doc, fecha_desde, fecha_hasta, organismo, cuenta_ascenso, observaciones,
                            origen, usuario_carga, suma_apn)
                       VALUES (?, ?, NULL, ?, 1, ?, 'importado_faltante', ?, 1)""",
                    (n_doc, fecha_desde_actual, organismo_actual,
                     "Período actual. " + ("Tomado de Antiguedad_LO." if fila_antig else
                                            "Antiguedad_LO no tenía registro; se usó la fecha de ingreso (DPersonales)."),
                     usuario),
                )
                registrar_auditoria(conn, "periodos_antiguedad", "INSERT", cur.lastrowid, None,
                                     {"n_doc": n_doc, "fecha_desde": fecha_desde_actual}, usuario)

            # ---- períodos anteriores: Nac_Priv ----
            for r in nac_priv_rows:
                if not r.get("N_doc") or not r["N_doc"].strip().isdigit() or int(r["N_doc"]) != n_doc:
                    continue
                fdesde = parse_fecha_access(r.get("Desde"))
                if not fdesde:
                    continue
                fhasta = parse_fecha_access(r.get("Hasta"))
                organismo = (r.get("Lugar") or "").strip()
                tipo_prestacion = (r.get("T_Pres") or "").strip()
                planta_nac = (r.get("Planta_Nac") or "").strip()
                motivo_baja = (r.get("Motivo_baja") or "").strip()
                suma_apn = 1 if (r.get("suma_ant") or "").strip() == "1" else 0

                cur = conn.execute(
                    """INSERT INTO periodos_antiguedad
                           (n_doc, fecha_desde, fecha_hasta, organismo, cuenta_ascenso, observaciones,
                            origen, usuario_carga, tipo_prestacion, suma_apn, planta_nac, motivo_baja)
                       VALUES (?, ?, ?, ?, 0, ?, 'importado_nac_priv', ?, ?, ?, ?, ?)""",
                    (n_doc, fdesde, fhasta, organismo,
                     "Importado desde Nac_Priv (servicio anterior). No cuenta para ascenso de grado 1421 por defecto.",
                     usuario, tipo_prestacion, suma_apn, planta_nac, motivo_baja),
                )
                registrar_auditoria(conn, "periodos_antiguedad", "INSERT", cur.lastrowid, None,
                                     {"n_doc": n_doc, "fecha_desde": fdesde, "organismo": organismo}, usuario)
                resumen["periodos_nacpriv_agregados"] += 1

            # ---- títulos ----
            for r in titulos_rows:
                if not r.get("N_doc") or not r["N_doc"].strip().isdigit() or int(r["N_doc"]) != n_doc:
                    continue
                id_niv = (r.get("Id_niv") or "").strip() or None
                titulo = (r.get("id_tit") or "").strip() or None
                institucion = (r.get("Institucion") or "").strip() or None
                fecha_egreso = parse_fecha_access(r.get("Fecha_egreso"))
                fecha_titulacion = parse_fecha_access(r.get("Fecha_Titulacion"))
                es_grado = 1 if id_niv == "U" else 0
                if not any([titulo, fecha_titulacion, institucion]):
                    continue
                cur = conn.execute(
                    """INSERT INTO titulos
                           (n_doc, id_niv, titulo, institucion, fecha_egreso, fecha_titulacion,
                            es_titulo_grado, origen)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'importado_faltante')""",
                    (n_doc, id_niv, titulo, institucion, fecha_egreso, fecha_titulacion, es_grado),
                )
                registrar_auditoria(conn, "titulos", "INSERT", cur.lastrowid, None,
                                     {"n_doc": n_doc, "titulo": titulo}, usuario)
                resumen["titulos_agregados"] += 1

        conn.execute(
            "INSERT OR REPLACE INTO metadata (clave, valor) VALUES ('migracion_agentes_faltantes_fecha', ?)",
            (datetime.now().isoformat(),),
        )

    return resumen


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("contratados_csv")
    ap.add_argument("listado_1421_csv")
    ap.add_argument("historico_csv")
    ap.add_argument("nivel_csv")
    ap.add_argument("asu_csv")
    ap.add_argument("dpersonales_csv")
    ap.add_argument("antig_lo_csv")
    ap.add_argument("nac_priv_csv")
    ap.add_argument("agente_titulo_csv")
    ap.add_argument("--usuario", default="migracion_agentes_faltantes")
    args = ap.parse_args()
    r = migrar(args.contratados_csv, args.listado_1421_csv, args.historico_csv, args.nivel_csv,
               args.asu_csv, args.dpersonales_csv, args.antig_lo_csv, args.nac_priv_csv,
               args.agente_titulo_csv, args.usuario)
    print("Resumen:")
    for k, v in r.items():
        print(f"  {k}: {v}")
