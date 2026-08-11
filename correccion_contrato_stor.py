"""
correccion_contrato_stor.py - Corrige contrato_desde_1421 de STOR,
Norberto Pablo (Documento 25.413.176).

Contexto: ese campo (traído de Listado_1421.INICIO_1421 en la migración
de agosto 2026) decía 01/04/2026, pero Ariel confirmó contra las fuentes
reales que la fecha correcta es 01/07/2026 -- coincide además con el
período de antigüedad ya vigente en el sistema (CONTRATADOS.Fecha de
alta), que nunca estuvo mal.

Este campo no se usa en ningún cálculo de antigüedad ni se muestra en
ninguna pantalla, menú o exportación del sistema (se verificó con
`grep` en todo el código): es sólo un dato informativo guardado en la
base. Corregirlo no cambia ningún resultado visible ni afecta ninguna
otra parte del sistema -- es pura prolijidad de los datos.

Es idempotente: si ya está corregido, no hace nada.
"""
from datetime import datetime

from db import init_db, Transaccion, registrar_auditoria, get_connection, row_to_dict

N_DOC = 25413176
FECHA_CORRECTA = "2026-07-01"
USUARIO = "correccion_contrato_stor"


def corregir():
    init_db()
    conn = get_connection()
    try:
        agente = conn.execute("SELECT * FROM agentes WHERE n_doc=?", (N_DOC,)).fetchone()
    finally:
        conn.close()

    if not agente:
        print(f"No se encontró el agente {N_DOC}.")
        return

    agente = row_to_dict(agente)
    if agente["contrato_desde_1421"] == FECHA_CORRECTA:
        print("Ya está corregido, no hace falta hacer nada.")
        return

    with Transaccion(f"correccion_contrato_stor_{N_DOC}") as conn:
        anterior = conn.execute("SELECT * FROM agentes WHERE n_doc=?", (N_DOC,)).fetchone()
        anterior = row_to_dict(anterior)
        conn.execute(
            "UPDATE agentes SET contrato_desde_1421=?, fecha_modif=?, usuario_modif=? WHERE n_doc=?",
            (FECHA_CORRECTA, datetime.now().isoformat(), USUARIO, N_DOC),
        )
        nuevo = {**anterior, "contrato_desde_1421": FECHA_CORRECTA}
        registrar_auditoria(conn, "agentes", "UPDATE", N_DOC, anterior, nuevo, USUARIO)

    print(f"Corregido: contrato_desde_1421 de STOR, Norberto Pablo "
          f"({anterior['contrato_desde_1421']} -> {FECHA_CORRECTA}).")


if __name__ == "__main__":
    corregir()
