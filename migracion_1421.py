"""
migracion_1421.py - Agrega la clasificación por régimen Decreto 1421/02
a la tabla `agentes`, sin tocar ningún dato existente (sólo ALTER TABLE
ADD COLUMN, que en SQLite es aditivo y no reescribe filas).

Luego clasifica a cada agente cruzando:
  - Listado_1421 / Historico 1421 / 1421 discriminado por nivel / ASU
    (del archivo Contratados_1421_-_2345_-_PNUD__2026.mdb)
      -> vinculado_1421 = 1 si aparece en alguna de esas tablas
  - CONTRATADOS (mismo archivo), campo "Fecha de baja"
      -> tiene_baja_1421 = 1 si tiene una fecha de baja registrada

  cuenta_1421 = 1  únicamente si vinculado_1421=1 Y tiene_baja_1421=0

Es idempotente: se puede correr de nuevo sin duplicar nada (usa UPDATE,
no INSERT), y cada corrida vuelve a evaluar la clasificación completa.

Uso:
    python migracion_1421.py /tmp/listado_1421.csv /tmp/historico_1421.csv \
        /tmp/1421_nivel.csv /tmp/asu.csv /tmp/contratados.csv --usuario Ariel
"""
import csv
import argparse
from datetime import datetime

from db import init_db, Transaccion, registrar_auditoria, get_connection, row_to_dict


def leer_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def docs_de(rows, col):
    s = set()
    for r in rows:
        v = r.get(col)
        if v and v.strip().isdigit():
            s.add(int(v))
    return s


def asegurar_columnas(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(agentes)")}
    agregados = []
    if "vinculado_1421" not in cols:
        conn.execute("ALTER TABLE agentes ADD COLUMN vinculado_1421 INTEGER NOT NULL DEFAULT 0")
        agregados.append("vinculado_1421")
    if "tiene_baja_1421" not in cols:
        conn.execute("ALTER TABLE agentes ADD COLUMN tiene_baja_1421 INTEGER NOT NULL DEFAULT 0")
        agregados.append("tiene_baja_1421")
    if "cuenta_1421" not in cols:
        conn.execute("ALTER TABLE agentes ADD COLUMN cuenta_1421 INTEGER NOT NULL DEFAULT 0")
        agregados.append("cuenta_1421")
    if "motivo_clasif_1421" not in cols:
        conn.execute("ALTER TABLE agentes ADD COLUMN motivo_clasif_1421 TEXT")
        agregados.append("motivo_clasif_1421")
    return agregados


def migrar(listado_1421_csv, historico_csv, nivel_csv, asu_csv, contratados_csv, usuario):
    init_db()

    docs_1421 = docs_de(leer_csv(listado_1421_csv), "doc_1421")
    docs_historico = docs_de(leer_csv(historico_csv), "doc_1421")
    docs_nivel = docs_de(leer_csv(nivel_csv), "Numero")
    docs_asu = docs_de(leer_csv(asu_csv), "NUMERO")
    union_1421 = docs_1421 | docs_historico | docs_nivel | docs_asu

    contratados_rows = leer_csv(contratados_csv)
    con_baja = set()
    for r in contratados_rows:
        if r.get("N_doc") and r["N_doc"].strip().isdigit():
            if r.get("Fecha de baja") and r["Fecha de baja"].strip():
                con_baja.add(int(r["N_doc"]))

    resumen = {
        "columnas_agregadas": [],
        "agentes_evaluados": 0,
        "vinculados_1421": 0,
        "excluidos_por_baja": 0,
        "cuentan_1421": 0,
        "no_vinculados": 0,
    }

    with Transaccion("migracion_1421") as conn:
        resumen["columnas_agregadas"] = asegurar_columnas(conn)

        agentes = conn.execute("SELECT n_doc, vinculado_1421, tiene_baja_1421, cuenta_1421, motivo_clasif_1421 FROM agentes").fetchall()

        for a in agentes:
            n_doc = a["n_doc"]
            vinculado = 1 if n_doc in union_1421 else 0
            baja = 1 if n_doc in con_baja else 0
            cuenta = 1 if (vinculado and not baja) else 0

            if vinculado and baja:
                motivo = "Vinculado a Decreto 1421/02, pero con Fecha de baja registrada en CONTRATADOS -> excluido"
            elif vinculado and not baja:
                motivo = "Vinculado a Decreto 1421/02, sin fecha de baja registrada -> cuenta para el sistema"
            else:
                motivo = "No aparece en ninguna tabla de origen del Decreto 1421/02 -> excluido"

            anterior = {"vinculado_1421": a["vinculado_1421"], "tiene_baja_1421": a["tiene_baja_1421"],
                        "cuenta_1421": a["cuenta_1421"], "motivo_clasif_1421": a["motivo_clasif_1421"]}
            nuevo = {"vinculado_1421": vinculado, "tiene_baja_1421": baja,
                     "cuenta_1421": cuenta, "motivo_clasif_1421": motivo}

            if anterior != nuevo:
                conn.execute(
                    """UPDATE agentes SET vinculado_1421=?, tiene_baja_1421=?, cuenta_1421=?,
                           motivo_clasif_1421=?, fecha_modif=?, usuario_modif=? WHERE n_doc=?""",
                    (vinculado, baja, cuenta, motivo, datetime.now().isoformat(), usuario, n_doc),
                )
                registrar_auditoria(conn, "agentes", "UPDATE", n_doc, anterior, nuevo, usuario)

            resumen["agentes_evaluados"] += 1
            resumen["vinculados_1421"] += vinculado
            resumen["excluidos_por_baja"] += (1 if (vinculado and baja) else 0)
            resumen["cuentan_1421"] += cuenta
            resumen["no_vinculados"] += (0 if vinculado else 1)

        conn.execute(
            "INSERT OR REPLACE INTO metadata (clave, valor) VALUES ('migracion_1421_fecha', ?)",
            (datetime.now().isoformat(),),
        )

    return resumen


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("listado_1421_csv")
    ap.add_argument("historico_csv")
    ap.add_argument("nivel_csv")
    ap.add_argument("asu_csv")
    ap.add_argument("contratados_csv")
    ap.add_argument("--usuario", default="migracion_1421")
    args = ap.parse_args()

    r = migrar(args.listado_1421_csv, args.historico_csv, args.nivel_csv,
               args.asu_csv, args.contratados_csv, args.usuario)
    print("Resumen de clasificación 1421:")
    for k, v in r.items():
        print(f"  {k}: {v}")
