"""
correccion_fecha_ingreso_schmidt.py - Corrige la fecha de ingreso del
período actual de SCHMIDT, Malvina Soledad (Documento 38.852.977).

Contexto: en agosto 2026 se corrigió para 38 agentes del lote "agentes
faltantes" el mismo problema (la fecha de ingreso importada desde
DPersonales.fecha_ing resultó ser una fecha de carga masiva, no la fecha
real de alta) reemplazándola por CONTRATADOS.Fecha de alta -- ver la
observación "Corregido: se usa CONTRATADOS.Fecha de alta..." en los
demás períodos de ese lote. Ese script (`remigrar_fecha_ingreso`, según
el motivo del backup automático del momento) corrigió 38 de los 39
agentes afectados, pero SCHMIDT quedó sin corregir.

Detectado por Ariel el 11/08/2026: el sistema mostraba 22/06/2026 como
inicio del período actual, cuando el alta real es 01/06/2026. Confirmado
además porque coincide con `contrato_desde_1421` (2026-06-01), que viene
de una fuente distinta (Listado_1421.INICIO_1421) y coincide con la
fecha corregida en prácticamente todos los demás casos del mismo lote
que resultaron ser altas nuevas (sin renovación previa).

Es idempotente: si ya se corrigió, no hace nada.
"""
from db import init_db, get_connection
import operaciones as ops

N_DOC = 38852977
FECHA_CORRECTA = "2026-06-01"
USUARIO = "correccion_fecha_ingreso_schmidt"


def corregir():
    init_db()
    conn = get_connection()
    try:
        periodo = conn.execute(
            "SELECT * FROM periodos_antiguedad WHERE n_doc=? AND fecha_hasta IS NULL AND activo=1",
            (N_DOC,),
        ).fetchone()
    finally:
        conn.close()

    if not periodo:
        print(f"No se encontró un período vigente para el agente {N_DOC}.")
        return

    if periodo["fecha_desde"] == FECHA_CORRECTA:
        print("Ya está corregido, no hace falta hacer nada.")
        return

    observacion_nueva = (
        f"Corregido manualmente (11/08/2026): la fecha de ingreso original "
        f"({periodo['fecha_desde']}) venía de DPersonales.fecha_ing, una fecha de "
        f"carga masiva y no la fecha real de alta -- mismo problema ya corregido "
        f"en agosto 2026 para otros 38 agentes del mismo lote (ver "
        f"'remigrar_fecha_ingreso' en el historial de backups), pero este caso "
        f"había quedado sin corregir. Se reemplaza por {FECHA_CORRECTA}, "
        f"confirmada por Ariel y coincidente con contrato_desde_1421 "
        f"(Listado_1421.INICIO_1421)."
    )

    ops.modificar_periodo(
        periodo["id"],
        USUARIO,
        fecha_desde=FECHA_CORRECTA,
        observaciones=observacion_nueva,
    )
    print(f"Corregido: período {periodo['id']} de SCHMIDT, Malvina Soledad "
          f"({periodo['fecha_desde']} -> {FECHA_CORRECTA}).")


if __name__ == "__main__":
    corregir()
