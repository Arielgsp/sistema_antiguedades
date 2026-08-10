"""
corregir_licencia_extraordinaria.py - Los campos Inicio/Finaliza de
Nac_Priv marcan un rango DENTRO de un período (Desde/Hasta) que Access
resta ("Menos días") sin importar el motivo (Sup, Ext, Licencia s/goce,
Nom x cuatrimestre, etc. -- confirmado por el usuario: SIEMPRE se resta).

Nuestro modelo de datos no soporta "huecos" dentro de un período, así
que se implementa partiendo el período original en dos:
  - [fecha_desde, Inicio - 1 día]
  - [Finaliza + 1 día, fecha_hasta]
con los mismos cuenta_ascenso / suma_apn / tipo_prestacion / organismo
que el período original. El período original se actualiza para
terminar antes de la licencia, y se inserta uno nuevo para lo que
sigue después. Todo con auditoría y sin borrar nada.

Alcance: sólo los 13 períodos (9 agentes) de Nac_Priv que caen dentro
del universo de 241 agentes del sistema y que ya fueron importados.
"""
import csv
from datetime import datetime, date, timedelta
from db import init_db, Transaccion, registrar_auditoria, get_connection

init_db()


def parse_fecha_access(valor):
    if not valor or not valor.strip():
        return None
    for fmt in ["%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S"]:
        try:
            dt = datetime.strptime(valor.strip(), fmt)
            if dt.year > datetime.now().year + 5:
                dt = dt.replace(year=dt.year - 100)
            return dt.date()
        except ValueError:
            continue
    return None


with open("/tmp/nac_priv.csv", newline="", encoding="utf-8") as f:
    nac_priv_rows = list(csv.DictReader(f))

con_licencia = [r for r in nac_priv_rows if r.get("Inicio", "").strip() and r.get("Finaliza", "").strip()]

resumen = {"revisados": 0, "partidos": 0, "sin_coincidencia": 0, "sin_espacio_para_partir": 0}

with Transaccion("corregir_licencia_extraordinaria") as conn:
    docs_sistema = {r["n_doc"] for r in conn.execute("SELECT n_doc FROM agentes WHERE cuenta_1421=1")}

    for r in con_licencia:
        if not r["N_doc"].isdigit() or int(r["N_doc"]) not in docs_sistema:
            continue
        resumen["revisados"] += 1
        n_doc = int(r["N_doc"])
        desde = parse_fecha_access(r["Desde"])
        hasta = parse_fecha_access(r["Hasta"])
        organismo = (r.get("Lugar") or "").strip()
        inicio_lic = parse_fecha_access(r["Inicio"])
        fin_lic = parse_fecha_access(r["Finaliza"])
        motivo = (r.get("T_ext_obs") or "").strip()

        # localizar el período ya importado que corresponde a esta fila de Nac_Priv
        fila = conn.execute(
            """SELECT * FROM periodos_antiguedad
                   WHERE n_doc=? AND fecha_desde=? AND organismo=? AND activo=1
                     AND origen IN ('importado_nac_priv')""",
            (n_doc, desde.isoformat(), organismo),
        ).fetchone()
        if not fila:
            resumen["sin_coincidencia"] += 1
            print(f"  SIN COINCIDENCIA: doc {n_doc}, {organismo}, desde {desde}")
            continue
        fila = dict(fila)

        primer_tramo_hasta = inicio_lic - timedelta(days=1)
        segundo_tramo_desde = fin_lic + timedelta(days=1)

        hay_primer_tramo = primer_tramo_hasta >= desde
        hay_segundo_tramo = hasta is not None and segundo_tramo_desde <= hasta

        if not hay_primer_tramo and not hay_segundo_tramo:
            resumen["sin_espacio_para_partir"] += 1
            print(f"  SIN ESPACIO: doc {n_doc}, {organismo} -- la licencia cubre todo el período")
            continue

        anterior = dict(fila)
        nota = (f"Partido por licencia extraordinaria/superposición interna "
                f"({inicio_lic.isoformat()} a {fin_lic.isoformat()}, motivo: {motivo or 'sin especificar'}). "
                f"{(fila.get('observaciones') or '').strip()}").strip()

        if hay_primer_tramo:
            conn.execute(
                "UPDATE periodos_antiguedad SET fecha_hasta=?, observaciones=?, fecha_modif=?, usuario_modif=? WHERE id=?",
                (primer_tramo_hasta.isoformat(), nota, datetime.now().isoformat(), "Ariel", fila["id"]),
            )
            registrar_auditoria(conn, "periodos_antiguedad", "UPDATE", fila["id"], anterior,
                                 {"fecha_hasta": primer_tramo_hasta.isoformat(), "motivo": "licencia extraordinaria"}, "Ariel")
        else:
            # la licencia empieza el mismo día que el período -> el "primer tramo" no existe,
            # desactivamos el período original y todo el contenido pasa al segundo tramo
            conn.execute(
                "UPDATE periodos_antiguedad SET activo=0, observaciones=?, fecha_modif=?, usuario_modif=? WHERE id=?",
                (nota + " [reemplazado por el tramo posterior a la licencia]", datetime.now().isoformat(), "Ariel", fila["id"]),
            )
            registrar_auditoria(conn, "periodos_antiguedad", "SOFT_DELETE", fila["id"], anterior,
                                 {"activo": 0, "motivo": "reemplazado por tramo posterior a licencia"}, "Ariel")

        if hay_segundo_tramo:
            cur = conn.execute(
                """INSERT INTO periodos_antiguedad
                       (n_doc, fecha_desde, fecha_hasta, organismo, cuenta_ascenso, observaciones,
                        origen, usuario_carga, tipo_prestacion, suma_apn, planta_nac, motivo_baja)
                   VALUES (?, ?, ?, ?, ?, ?, 'importado_nac_priv', ?, ?, ?, ?, ?)""",
                (n_doc, segundo_tramo_desde.isoformat(), hasta.isoformat() if hasta else None, organismo,
                 fila["cuenta_ascenso"], nota, "Ariel", fila.get("tipo_prestacion"), fila.get("suma_apn"),
                 fila.get("planta_nac"), fila.get("motivo_baja")),
            )
            registrar_auditoria(conn, "periodos_antiguedad", "INSERT", cur.lastrowid, None,
                                 {"n_doc": n_doc, "fecha_desde": segundo_tramo_desde.isoformat(),
                                  "motivo": "tramo posterior a licencia extraordinaria"}, "Ariel")

        resumen["partidos"] += 1

    conn.execute(
        "INSERT OR REPLACE INTO metadata (clave, valor) VALUES ('correccion_licencia_extraordinaria_fecha', ?)",
        (datetime.now().isoformat(),),
    )

print("Resumen:")
for k, v in resumen.items():
    print(f"  {k}: {v}")
