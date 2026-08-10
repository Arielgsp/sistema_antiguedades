"""
cli.py - Menú interactivo del Sistema de Antigüedad y Ascensos de Grado.

Ejecutar con:  python cli.py
"""

import sys
from datetime import date

from db import init_db, verificar_integridad, DB_PATH, BACKUP_DIR, backup_antes_de_escribir
import operaciones as ops


def pedir(msg, default=None, obligatorio=False):
    suf = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"{msg}{suf}: ").strip()
        if not val and default is not None:
            return default
        if not val and obligatorio:
            print("  (obligatorio, no puede quedar vacío)")
            continue
        return val or None


def pedir_fecha(msg, default=None, obligatorio=False):
    while True:
        val = pedir(msg + " (AAAA-MM-DD)", default, obligatorio)
        if val is None:
            return None
        try:
            date.fromisoformat(val)
            return val
        except ValueError:
            print("  Formato inválido. Usar AAAA-MM-DD, ej: 2024-05-01")


def pedir_si_no(msg, default=True):
    d = "S" if default else "N"
    while True:
        val = input(f"{msg} (S/N) [{d}]: ").strip().upper()
        if not val:
            return default
        if val in ("S", "SI", "SÍ"):
            return True
        if val in ("N", "NO"):
            return False


def elegir_agente(solo_1421=True):
    texto = pedir("Buscar agente por apellido o N° de documento", obligatorio=True)
    resultados = ops.buscar_agentes(texto, incluir_inactivos=True, solo_1421=solo_1421)
    if not resultados:
        extra = " dentro del universo Decreto 1421/02 (198 agentes)" if solo_1421 else ""
        print(f"No se encontraron agentes{extra}.")
        if solo_1421:
            print("Tip: opción 11 del menú para revisar por qué un agente no cuenta en 1421.")
        return None
    if len(resultados) > 1:
        print(f"\nSe encontraron {len(resultados)} coincidencias:")
        for i, a in enumerate(resultados, 1):
            estado = "" if a["activo"] else " [INACTIVO]"
            print(f"  {i}. {a['apellido_nombre']} - Doc {a['n_doc']}{estado}")
        idx = pedir("Elegí un número", obligatorio=True)
        try:
            return resultados[int(idx) - 1]["n_doc"]
        except (ValueError, IndexError):
            print("Selección inválida.")
            return None
    return resultados[0]["n_doc"]


def mostrar_ficha(n_doc):
    a = ops.obtener_agente(n_doc)
    if not a:
        print("Agente no encontrado.")
        return
    print("\n" + "=" * 70)
    print(f" {a['apellido_nombre']}  —  Documento: {a['n_doc']}")
    print("=" * 70)
    print(f" Activo: {'Sí' if a['activo'] else 'No'}   Nivel actual: {a['nivel_actual']}   Grado actual: {a['grado_actual']}")

    cfg = a["config"] or {}
    print(f"\n Configuración de cómputo de grado:")
    print(f"   Fecha inicio de conteo (override): {cfg.get('fecha_inicio_conteo_grado') or '(usa fecha_desde de los períodos)'}")
    print(f"   Fecha de cierre de conteo:          {cfg.get('fecha_cierre_conteo') or '(sin cierre, cuenta hasta hoy)'}")
    print(f"   Grado base:                          {cfg.get('grado_base', 0)}")

    print(f"\n Períodos de antigüedad ({len(a['periodos'])}):")
    if not a["periodos"]:
        print("   (sin períodos cargados)")
    for p in a["periodos"]:
        cuenta = "CUENTA" if p["cuenta_ascenso"] else "NO CUENTA"
        hasta = p["fecha_hasta"] or "vigente"
        print(f"   [id {p['id']}] {p['fecha_desde']} -> {hasta}  | {cuenta}  | {p['organismo'] or ''}")

    print(f"\n Títulos de grado (universitarios):")
    if not a["titulos_grado"]:
        print("   (no registra título de grado)")
    for t in a["titulos_grado"]:
        print(f"   {t['titulo'] or '(sin especificar)'} - {t['institucion'] or ''} - Titulación: {t['fecha_titulacion'] or 'sin fecha'}")

    if a["titulos"] and len(a["titulos"]) > len(a["titulos_grado"]):
        print(f"\n Otros títulos registrados: {len(a['titulos']) - len(a['titulos_grado'])}")

    calc = ops.calcular_antiguedad_agente(n_doc)
    print(f"\n Antigüedad computable a hoy ({calc['fecha_corte']}): {calc['antiguedad_texto']}")
    print("=" * 70 + "\n")


def menu_ver_agente():
    n_doc = elegir_agente()
    if n_doc:
        mostrar_ficha(n_doc)


def menu_cargar_periodo():
    n_doc = elegir_agente()
    if not n_doc:
        return
    mostrar_ficha(n_doc)
    print("Cargar nuevo período de antigüedad:")
    fecha_desde = pedir_fecha("Fecha desde", obligatorio=True)
    tiene_hasta = pedir_si_no("¿Tiene fecha de fin (cerrado)?", default=False)
    fecha_hasta = pedir_fecha("Fecha hasta") if tiene_hasta else None
    organismo = pedir("Organismo / dependencia de ese período")
    cuenta = pedir_si_no("¿Este período CUENTA para el ascenso de grado?", default=True)
    obs = pedir("Observaciones")
    usuario = pedir("Tu nombre/usuario (para el registro de auditoría)", obligatorio=True)

    pid = ops.cargar_periodo(n_doc, fecha_desde, fecha_hasta, organismo, cuenta, obs, usuario)
    print(f"\n✓ Período cargado con id {pid}. Backup automático creado antes de guardar.\n")


def menu_modificar_periodo():
    n_doc = elegir_agente()
    if not n_doc:
        return
    mostrar_ficha(n_doc)
    pid = pedir("ID del período a modificar", obligatorio=True)
    try:
        pid = int(pid)
    except ValueError:
        print("ID inválido.")
        return

    print("Dejá en blanco lo que no quieras cambiar.")
    cambios = {}
    fd = pedir_fecha("Nueva fecha desde")
    if fd:
        cambios["fecha_desde"] = fd
    fh = pedir("¿Modificar fecha hasta? (S/N)", default="N")
    if fh and fh.upper() == "S":
        cambios["fecha_hasta"] = pedir_fecha("Nueva fecha hasta (vacío = vigente/abierto)")
    org = pedir("Nuevo organismo")
    if org:
        cambios["organismo"] = org
    cambia_cuenta = pedir("¿Cambiar si cuenta para ascenso? (S/N)", default="N")
    if cambia_cuenta and cambia_cuenta.upper() == "S":
        cambios["cuenta_ascenso"] = int(pedir_si_no("¿Cuenta para ascenso?", default=True))
    obs = pedir("Nuevas observaciones")
    if obs:
        cambios["observaciones"] = obs

    usuario = pedir("Tu nombre/usuario", obligatorio=True)
    if not cambios:
        print("No se indicaron cambios.")
        return
    ops.modificar_periodo(pid, usuario, **cambios)
    print("\n✓ Período modificado. Backup automático creado antes de guardar.\n")


def menu_marcar_cuenta():
    n_doc = elegir_agente()
    if not n_doc:
        return
    mostrar_ficha(n_doc)
    pid = pedir("ID del período a marcar", obligatorio=True)
    try:
        pid = int(pid)
    except ValueError:
        print("ID inválido.")
        return
    cuenta = pedir_si_no("¿Este período debe CONTAR para el ascenso de grado?", default=True)
    usuario = pedir("Tu nombre/usuario", obligatorio=True)
    ops.marcar_cuenta_ascenso(pid, cuenta, usuario)
    print("\n✓ Actualizado.\n")


def menu_config_agente():
    n_doc = elegir_agente()
    if not n_doc:
        return
    mostrar_ficha(n_doc)
    print("Configuración de cómputo (dejar en blanco = no modificar):")
    inicio = pedir_fecha("Fecha desde la cual se debe contar el grado (override)")
    cierre = pedir_fecha("Fecha de cierre hasta la cual se debe contar el grado")
    grado_base = pedir("Grado base de partida (si no arranca en 0)")
    grado_base = int(grado_base) if grado_base else None
    obs = pedir("Observaciones")
    usuario = pedir("Tu nombre/usuario", obligatorio=True)

    ops.set_config_agente(n_doc, usuario, fecha_inicio_conteo_grado=inicio,
                           fecha_cierre_conteo=cierre, grado_base=grado_base, observaciones=obs)
    print("\n✓ Configuración guardada.\n")


def menu_desactivar_periodo():
    n_doc = elegir_agente()
    if not n_doc:
        return
    mostrar_ficha(n_doc)
    pid = pedir("ID del período a desactivar (NO se borra, queda inactivo y en el historial)", obligatorio=True)
    try:
        pid = int(pid)
    except ValueError:
        print("ID inválido.")
        return
    motivo = pedir("Motivo de la desactivación", obligatorio=True)
    usuario = pedir("Tu nombre/usuario", obligatorio=True)
    ops.desactivar_periodo(pid, usuario, motivo)
    print("\n✓ Período desactivado (soft-delete, se conserva en el historial y en auditoría).\n")


def menu_crear_agente():
    n_doc = pedir("N° de documento del nuevo agente", obligatorio=True)
    try:
        n_doc = int(n_doc)
    except ValueError:
        print("Documento inválido.")
        return
    nombre = pedir("Apellido y Nombre", obligatorio=True)
    nivel = pedir("Nivel actual (A-F, opcional)")
    grado = pedir("Grado actual (opcional)")
    grado = int(grado) if grado else None
    usuario = pedir("Tu nombre/usuario", obligatorio=True)
    try:
        ops.crear_agente_manual(n_doc, nombre, usuario, nivel, grado)
        print("\n✓ Agente creado.\n")
    except ValueError as e:
        print(f"\n✗ Error: {e}\n")


def menu_ascensos_anio():
    anio = pedir("Año a evaluar (se calcula al 31/12 de ese año)", obligatorio=True)
    try:
        anio = int(anio)
    except ValueError:
        print("Año inválido.")
        return
    print(f"\nCalculando ascensos al 31/12/{anio}... (puede tardar unos segundos)\n")
    resultados = ops.listar_ascensos_anio(anio)
    if not resultados:
        print(f"Nadie asciende según el corte del 31/12/{anio}.\n")
        return
    print(f"Agentes que ASCIENDEN según el corte del 31/12/{anio} (efectivo 01/01/{anio+1}):\n")
    for r in resultados:
        print(f"  {r['apellido_nombre']} (Doc {r['n_doc']}): "
              f"{r['grados_anio_anterior']} -> {r['grados_acumulados']} grado(s) "
              f"(+{r['grados_nuevos']})  |  antigüedad: {r['antiguedad_computable_texto']}")
    print(f"\nTotal: {len(resultados)} agentes.\n")

    guardar = pedir_si_no("¿Guardar esta corrida en el historial de cálculos (auditable)?", default=True)
    if guardar:
        usuario = pedir("Tu nombre/usuario", obligatorio=True)
        for r in resultados:
            ops.evaluar_ascenso_agente(r["n_doc"], anio, persistir=True, usuario=usuario)
        print("✓ Corrida guardada en calculos_ascenso.\n")


def menu_verificar_integridad():
    ok, detalle = verificar_integridad()
    print(f"\nIntegridad de la base: {'OK' if ok else 'PROBLEMA DETECTADO'}")
    print(f"Detalle: {detalle}")
    print(f"Archivo: {DB_PATH}")
    backups = sorted(BACKUP_DIR.glob("*.db"))
    print(f"Backups disponibles: {len(backups)}")
    if backups:
        print(f"  Último backup: {backups[-1].name}")
    print()


def menu_backup_manual():
    destino = backup_antes_de_escribir("manual")
    print(f"\n✓ Backup creado: {destino}\n")


def menu_resumen_1421():
    r = ops.resumen_clasificacion_1421()
    print("\n" + "=" * 60)
    print(" CLASIFICACIÓN POR DECRETO 1421/02")
    print("=" * 60)
    print(f" Total de agentes en el sistema:                    {r['total_agentes']}")
    print(f" Vinculados a alguna tabla de origen 1421:           {r['vinculados_1421']}")
    print(f"   de los cuales, con Fecha de baja (excluidos):     {r['excluidos_por_baja']}")
    print(f" No vinculados a 1421 (excluidos):                   {r['no_vinculados']}")
    print(f" TOTAL QUE CUENTA (cuenta_1421=1):                   {r['cuentan_1421']}")
    print("=" * 60)
    print(" Todos los reportes y menús de este sistema, por defecto,")
    print(" sólo consideran a los agentes marcados cuenta_1421=1.")
    print("=" * 60 + "\n")

    ver_detalle = pedir_si_no("¿Consultar la clasificación de un agente puntual?", default=False)
    if ver_detalle:
        n_doc = elegir_agente(solo_1421=False)
        if n_doc:
            c = ops.clasificacion_1421(n_doc)
            print(f"\n{c['apellido_nombre']} (Doc {c['n_doc']})")
            print(f"  Vinculado a 1421: {'Sí' if c['vinculado_1421'] else 'No'}")
            print(f"  Tiene fecha de baja: {'Sí' if c['tiene_baja_1421'] else 'No'}")
            print(f"  Cuenta para el sistema: {'Sí' if c['cuenta_1421'] else 'No'}")
            print(f"  Motivo: {c['motivo_clasif_1421']}\n")


MENU = """
============================================================
  SISTEMA DE ANTIGÜEDAD Y ASCENSOS DE GRADO
  (Decreto 1421/02 — universo filtrado: 198 agentes)
============================================================
  1. Ver ficha de un agente (antigüedad, títulos, config)
  2. Cargar nuevo período de antigüedad
  3. Modificar un período existente
  4. Marcar si un período cuenta o no para el ascenso
  5. Configurar fecha de inicio / cierre de cómputo de grado
  6. Desactivar un período (no se borra, queda en historial)
  7. Crear un agente nuevo (manual)
  8. Ver quiénes ASCIENDEN en un año determinado
  9. Verificar integridad de la base / ver backups
  10. Hacer backup manual ahora
  11. Ver resumen de clasificación 1421 / consultar un caso puntual
  0. Salir
============================================================
"""


def main():
    init_db()
    ok, detalle = verificar_integridad()
    if not ok:
        print(f"¡ATENCIÓN! La base reporta un problema de integridad: {detalle}")
        print("Se recomienda restaurar desde el último backup antes de continuar.")
        if not pedir_si_no("¿Continuar de todos modos?", default=False):
            sys.exit(1)

    acciones = {
        "1": menu_ver_agente,
        "2": menu_cargar_periodo,
        "3": menu_modificar_periodo,
        "4": menu_marcar_cuenta,
        "5": menu_config_agente,
        "6": menu_desactivar_periodo,
        "7": menu_crear_agente,
        "8": menu_ascensos_anio,
        "9": menu_verificar_integridad,
        "10": menu_backup_manual,
        "11": menu_resumen_1421,
    }

    while True:
        print(MENU)
        opcion = input("Elegí una opción: ").strip()
        if opcion == "0":
            print("Hasta luego.")
            break
        accion = acciones.get(opcion)
        if not accion:
            print("Opción inválida.\n")
            continue
        try:
            accion()
        except Exception as e:
            print(f"\n✗ ERROR: {e}")
            print("No se guardó ningún cambio parcial (la transacción se revirtió automáticamente).\n")


if __name__ == "__main__":
    main()
