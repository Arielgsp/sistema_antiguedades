"""Prueba headless de gui.py bajo Xvfb."""
import tkinter as tk
from tkinter import simpledialog
from pathlib import Path

# limpiar usuario local guardado de corridas anteriores, para que la
# prueba sea repetible (si no, el diálogo de bienvenida real se traba
# esperando un clic que nunca llega en modo headless)
Path(__file__).resolve().parent.joinpath("data", "usuario_local.txt").unlink(missing_ok=True)

import gui

simpledialog.askstring = lambda *a, **k: "Tester Automatico"

app = gui.App()
app.update()
print("Ventana creada OK. Título:", app.title())
print("Usuario:", app.usuario)

# Buscar POLLORA (caso ya validado contra Access)
app.entry_buscar.insert(0, "POLLORA")
app.accion_buscar()
app.update()
hijos = app.tree_agentes.get_children()
assert len(hijos) == 1
app.tree_agentes.selection_set(hijos[0])
app.accion_seleccionar_agente()
app.update()
assert app.lbl_total_1421.cget("text") == "12 años 29 días"
assert "15 años 2 meses" in app.lbl_total_apn.cget("text")
assert "Contrato 1421 vigente" not in app.lbl_ficha_sub2.cget("text")
print("OK: ficha de POLLORA correcta (Nivel A -> cuenta desde fecha de titulación 03/12/2014 "
      "por la nueva regla por defecto), sin línea de contrato")

# Probar "Mostrar todos" (reset del buscador)
app.accion_limpiar_busqueda()
app.update()
total_todos = len(app.tree_agentes.get_children())
print("Total mostrado con 'Mostrar todos':", total_todos)
assert total_todos == 241, f"Se esperaban 241 agentes, se mostraron {total_todos}"
print("OK: el botón 'Mostrar todos' resetea el buscador")

# Verificar los 2 agentes que antes faltaban
for nombre, doc in [("JAIMES", 34167094), ("CRUZ", 32475277)]:
    app.entry_buscar.delete(0, "end")
    app.entry_buscar.insert(0, nombre)
    app.accion_buscar()
    app.update()
    encontrados = app.tree_agentes.get_children()
    assert str(doc) in encontrados, f"{nombre} no se encontró"
    print(f"OK: {nombre} ({doc}) encontrado en el buscador")

# Editar datos de agente (nivel/grado/dependencia) -- usando un agente
# de PRUEBA dedicado (nunca sobre una persona real) para no contaminar
# datos reales del sistema.
import operaciones as ops
TEST_DOC = 99999002
from db import get_connection
conn = get_connection()
conn.execute("DELETE FROM titulos WHERE n_doc=?", (TEST_DOC,))
conn.execute("DELETE FROM periodos_antiguedad WHERE n_doc=?", (TEST_DOC,))
conn.execute("DELETE FROM config_agente WHERE n_doc=?", (TEST_DOC,))
conn.execute("DELETE FROM agentes WHERE n_doc=?", (TEST_DOC,))
conn.commit(); conn.close()
ops.crear_agente_manual(TEST_DOC, "PRUEBA GUI, Test", "test_gui_script")
conn = get_connection()
conn.execute("UPDATE agentes SET cuenta_1421=1 WHERE n_doc=?", (TEST_DOC,))
conn.commit(); conn.close()

app.entry_buscar.delete(0, "end")
app.entry_buscar.insert(0, "PRUEBA GUI")
app.accion_buscar()
app.update()
app.tree_agentes.selection_set(str(TEST_DOC))
app.accion_seleccionar_agente()
app.update()

def fake_form_editar(*a, **k):
    return {"nivel": "B", "grado": "5", "dependencia": "Dependencia de prueba"}
gui.pedir_formulario = fake_form_editar
app.accion_editar_agente()
app.update()
assert "B" in app.lbl_ficha_sub.cget("text") and "5" in app.lbl_ficha_sub.cget("text")
print("OK: edición de Nivel/Grado/Dependencia funciona")
print("Ficha tras editar:", app.lbl_ficha_sub.cget("text"))

# Editar título y usar "contar desde fecha de titulación"
def fake_form_titulo(*a, **k):
    return {"titulo": "Lic. en Prueba", "institucion": "UBA", "fecha_titulacion": "2015-06-01", "fecha_egreso": ""}
gui.pedir_formulario = fake_form_titulo
app.accion_editar_titulo()
app.update()
print("Títulos tras editar:", app.lbl_titulos.cget("text"))
assert "Lic. en Prueba" in app.lbl_titulos.cget("text")

import tkinter.messagebox as mb
mb.askyesno = lambda *a, **k: True
app.accion_usar_fecha_titulacion()
app.update()
print("Config tras usar fecha de titulación:", app.lbl_config.cget("text"))
assert "01/06/2015" in app.lbl_config.cget("text")
print("OK: 'contar desde fecha de titulación' funciona")

# limpiar el agente de prueba
conn = get_connection()
conn.execute("DELETE FROM auditoria WHERE registro_id=? OR valor_nuevo LIKE ?", (str(TEST_DOC), f'%{TEST_DOC}%'))
conn.execute("DELETE FROM titulos WHERE n_doc=?", (TEST_DOC,))
conn.execute("DELETE FROM periodos_antiguedad WHERE n_doc=?", (TEST_DOC,))
conn.execute("DELETE FROM config_agente WHERE n_doc=?", (TEST_DOC,))
conn.execute("DELETE FROM agentes WHERE n_doc=?", (TEST_DOC,))
conn.commit(); conn.close()
print("OK: agente de prueba eliminado, no queda en la base final")

# Ascensos con fecha de corte personalizada
app.entry_fecha_corte_ascensos.delete(0, "end")
app.entry_fecha_corte_ascensos.insert(0, "2026-06-30")
app.accion_calcular_ascensos()
app.update()
print("Ascensos al 2026-06-30:", len(app.tree_ascensos.get_children()), "-", app.lbl_ascensos_resumen.cget("text"))

# fecha de corte automática dinámica
r = gui.ops.obtener_fecha_corte_oficial()
print("Fecha de corte automática (backend):", r)
assert r.year == 2026 and r.month == 12 and r.day == 31

app.destroy()
print("\nTODAS LAS PRUEBAS DE LA INTERFAZ VISUAL PASARON CORRECTAMENTE")
