"""Pruebas automáticas (no interactivas) del sistema completo."""
import sqlite3
from datetime import date
import operaciones as ops
from db import get_connection, verificar_integridad, DB_PATH

def linea(msg):
    print(f"\n--- {msg} ---")

# 1) Integridad general
linea("1) Integridad de la base recién importada")
ok, detalle = verificar_integridad()
assert ok, f"Integridad falló: {detalle}"
print("OK:", detalle)

# 2) Ficha de un agente real con período abierto desde 1992
linea("2) Ficha de MONTAGNA (11154879)")
a = ops.obtener_agente(11154879)
assert a is not None
print(a["apellido_nombre"], "- periodos:", len(a["periodos"]))
calc = ops.calcular_antiguedad_agente(11154879, date(2025,12,31))
print("Antigüedad al 31/12/2025:", calc["antiguedad_texto"])

# 3) Crear agente de prueba manual
linea("3) Crear agente de prueba")
TEST_DOC = 99999001
conn = get_connection()
conn.execute("DELETE FROM auditoria WHERE registro_id=?", (str(TEST_DOC),))
conn.execute("DELETE FROM periodos_antiguedad WHERE n_doc=?", (TEST_DOC,))
conn.execute("DELETE FROM config_agente WHERE n_doc=?", (TEST_DOC,))
conn.execute("DELETE FROM agentes WHERE n_doc=?", (TEST_DOC,))
conn.commit(); conn.close()

ops.crear_agente_manual(TEST_DOC, "PRUEBA, Test", "test_script")
print("Agente de prueba creado.")

# 4) Cargar período principal (ejemplo del usuario: ingreso 1/5/2023)
linea("4) Cargar período 2023-05-01 (vigente, cuenta)")
pid1 = ops.cargar_periodo(TEST_DOC, "2023-05-01", None, "Ministerio de Defensa", True, "período principal", "test_script")
print("Periodo id:", pid1)

r2026 = ops.evaluar_ascenso_agente(TEST_DOC, 2026)
print("Evaluación 2026:", r2026["antiguedad_computable_texto"], "asciende:", r2026["asciende"], "efectivo:", r2026["fecha_efectiva_ascenso"])
assert r2026["asciende"] is True
assert r2026["fecha_efectiva_ascenso"] == "2027-01-01"
print("OK: coincide con el ejemplo del usuario (ascenso efectivo 2027-01-01)")

# 5) Cargar un segundo período (anterior, no vigente) que NO cuenta
linea("5) Cargar período anterior que NO cuenta para ascenso")
pid2 = ops.cargar_periodo(TEST_DOC, "2015-01-01", "2018-01-01", "Otro organismo (no reconocido)", False, "no cuenta - decisión administrativa", "test_script")
r2026_b = ops.evaluar_ascenso_agente(TEST_DOC, 2026)
assert r2026_b["antiguedad_computable_dias"] == r2026["antiguedad_computable_dias"], "El período no marcado no debería sumar"
print("OK: el período marcado 'no cuenta' no afecta el cómputo")

# 6) Ahora lo marcamos que SÍ cuenta y verificamos que el cómputo cambia
linea("6) Marcar el período anterior como que SÍ cuenta")
ops.marcar_cuenta_ascenso(pid2, True, "test_script")
r2026_c = ops.evaluar_ascenso_agente(TEST_DOC, 2026)
print("Antigüedad con el período anterior sumando:", r2026_c["antiguedad_computable_texto"])
assert r2026_c["antiguedad_computable_dias"] > r2026["antiguedad_computable_dias"]
print("OK: al marcarlo que cuenta, la antigüedad aumenta")

# 7) Config: fecha de cierre de cómputo (tope)
linea("7) Fecha de cierre de cómputo (tope al 2024-12-31)")
ops.set_config_agente(TEST_DOC, "test_script", fecha_cierre_conteo="2024-12-31")
r_con_cierre = ops.evaluar_ascenso_agente(TEST_DOC, 2026)
print("Con cierre al 2024-12-31:", r_con_cierre["antiguedad_computable_texto"], "asciende:", r_con_cierre["asciende"])
assert r_con_cierre["asciende"] is False, "Con el cierre, no debería llegar a los 3 años todavía"
print("OK: el cierre de cómputo limita correctamente la antigüedad")

# quitar el cierre para seguir probando
ops.set_config_agente(TEST_DOC, "test_script", fecha_cierre_conteo="")

# 8) Soft-delete de un período: NO debe desaparecer de la tabla, sólo activo=0
linea("8) Desactivar (soft-delete) el período anterior")
ops.desactivar_periodo(pid2, "test_script", "prueba de soft-delete")
conn = get_connection()
row = conn.execute("SELECT activo FROM periodos_antiguedad WHERE id=?", (pid2,)).fetchone()
conn.close()
assert row["activo"] == 0
print("OK: el período sigue existiendo en la tabla, sólo con activo=0 (no se perdió el dato)")

a2 = ops.obtener_agente(TEST_DOC)
assert all(p["id"] != pid2 for p in a2["periodos"]), "El listado activo no debe mostrar el desactivado"
print("OK: el listado de períodos activos ya no lo muestra, pero el registro persiste en la BD")

# 9) Prueba de ROLLBACK: forzar un error a mitad de una transacción
linea("9) Prueba de ROLLBACK ante error (no debe quedar nada a medias)")
from db import Transaccion, registrar_auditoria
conn_check_antes = get_connection()
cant_periodos_antes = conn_check_antes.execute("SELECT COUNT(*) c FROM periodos_antiguedad").fetchone()["c"]
conn_check_antes.close()

try:
    with Transaccion("test_rollback") as conn:
        conn.execute(
            """INSERT INTO periodos_antiguedad (n_doc, fecha_desde, cuenta_ascenso, usuario_carga)
               VALUES (?, ?, 1, 'test_script')""",
            (TEST_DOC, "2020-01-01"),
        )
        # Forzamos un error deliberado (referencia a agente inexistente -> viola FK)
        conn.execute(
            """INSERT INTO periodos_antiguedad (n_doc, fecha_desde, cuenta_ascenso, usuario_carga)
               VALUES (?, ?, 1, 'test_script')""",
            (888888888, "2020-01-01"),  # n_doc que no existe en agentes -> FK error
        )
except sqlite3.IntegrityError as e:
    print("Error esperado capturado:", e)

conn_check_despues = get_connection()
cant_periodos_despues = conn_check_despues.execute("SELECT COUNT(*) c FROM periodos_antiguedad").fetchone()["c"]
conn_check_despues.close()
assert cant_periodos_antes == cant_periodos_despues, "¡FALLO DE ROBUSTEZ! quedó un insert parcial"
print(f"OK: períodos antes={cant_periodos_antes}, después={cant_periodos_despues} -> el ROLLBACK funcionó, nada quedó a medias")

# 10) Auditoría: debe haber una fila por cada operación de escritura sobre TEST_DOC
linea("10) Verificar auditoría completa del agente de prueba")
conn = get_connection()
aud = conn.execute("SELECT operacion, tabla FROM auditoria WHERE valor_nuevo LIKE ? OR registro_id=?",
                    (f'%{TEST_DOC}%', str(TEST_DOC))).fetchall()
conn.close()
print(f"Filas de auditoría relacionadas al agente de prueba: {len(aud)}")
for r in aud:
    print("  ", r["operacion"], r["tabla"])
assert len(aud) >= 5
print("OK: hay rastro de auditoría de cada cambio")

# 11) Integridad final
linea("11) Integridad final de la base")
ok, detalle = verificar_integridad()
assert ok
print("OK:", detalle)

# 12) Regresión: cuenta_1421=1 siempre debe implicar activo=1
linea("12) Regresión: nadie con cuenta_1421=1 debe tener activo=0")
conn = get_connection()
r = conn.execute("SELECT COUNT(*) c FROM agentes WHERE cuenta_1421=1 AND activo=0").fetchone()
conn.close()
assert r["c"] == 0, f"¡Hay {r['c']} agentes vigentes (cuenta_1421=1) marcados como inactivos! Bug de 'Ascensos por año'."
print("OK: todos los agentes vigentes están marcados activos")

# 13) Regresión: suma_apn sólo debe ser 0 para tipo 'Priv' (períodos importados de Nac_Priv)
linea("13) Regresión: suma_apn=0 sólo debe darse en periodos tipo 'Priv'")
conn = get_connection()
mal = conn.execute("""
    SELECT COUNT(*) c FROM periodos_antiguedad
    WHERE origen='importado_nac_priv' AND activo=1
      AND ((suma_apn=0 AND tipo_prestacion!='Priv') OR (suma_apn=1 AND tipo_prestacion='Priv'))
""").fetchone()
conn.close()
assert mal["c"] == 0, f"¡Hay {mal['c']} períodos con suma_apn mal calculado según el tipo!"
print("OK: suma_apn coincide con la regla (todo cuenta excepto 'Priv')")

# Limpieza del agente de prueba (dejamos la base real intacta)
linea("Limpieza: eliminando agente de prueba")
conn = get_connection()
conn.execute("DELETE FROM auditoria WHERE registro_id=? OR valor_nuevo LIKE ?", (str(TEST_DOC), f'%{TEST_DOC}%'))
conn.execute("DELETE FROM periodos_antiguedad WHERE n_doc=?", (TEST_DOC,))
conn.execute("DELETE FROM config_agente WHERE n_doc=?", (TEST_DOC,))
conn.execute("DELETE FROM agentes WHERE n_doc=?", (TEST_DOC,))
conn.commit()
conn.close()

print("\n============================================")
print(" TODAS LAS PRUEBAS PASARON CORRECTAMENTE")
print("============================================")
