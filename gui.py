"""
gui.py - Interfaz visual del Sistema de Antigüedad y Ascensos de Grado
(Decreto 1421/02). Rediseñada para que la ficha de cada agente se lea
igual que el reporte de Access: Nivel y Grado, título, cada período de
antigüedad con su propio desglose de años/meses/días, y los DOS totales
que importan (Administración Pública Nacional vs. ascenso de grado 1421).

Sólo muestra a los agentes que cuentan bajo el Decreto 1421/02 -- el
resto de la base de personal (irrelevante para este sistema) no
aparece en ningún listado.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import date, datetime, timedelta

from db import init_db, verificar_integridad, backup_antes_de_escribir, DB_PATH, BACKUP_DIR
import operaciones as ops
import exportar
import usuario_local
from antiguedad import texto_antiguedad

COLOR_HEADER = "#1F4E78"
COLOR_ACCENT = "#2E7D89"
COLOR_BG = "#F5F7FA"
COLOR_BOX_APN = "#EAECEE"
COLOR_BOX_1421 = "#DCEEF2"
COLOR_OK = "#1E7A34"
COLOR_NO = "#8A8A8A"
FONT_BASE = ("Segoe UI", 10)
FONT_TITULO = ("Segoe UI", 15, "bold italic")
FONT_SECCION = ("Segoe UI", 10, "bold")
FONT_TOTAL_LABEL = ("Segoe UI", 10)
FONT_TOTAL_VALOR = ("Segoe UI", 13, "bold")


class FormularioDialogo(simpledialog.Dialog):
    def __init__(self, parent, titulo, campos, ayuda=None):
        self.campos = campos
        self.ayuda = ayuda
        self.entradas = {}
        self.resultado = None
        super().__init__(parent, title=titulo)

    def body(self, master):
        master.configure(bg=COLOR_BG)
        if self.ayuda:
            tk.Label(master, text=self.ayuda, wraplength=420, justify="left",
                     fg="#444", bg=COLOR_BG).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
            offset = 1
        else:
            offset = 0
        for i, (clave, etiqueta, valor) in enumerate(self.campos):
            tk.Label(master, text=etiqueta, bg=COLOR_BG).grid(row=i + offset, column=0, sticky="e", padx=5, pady=4)
            e = tk.Entry(master, width=32)
            e.insert(0, valor or "")
            e.grid(row=i + offset, column=1, padx=5, pady=4)
            self.entradas[clave] = e
        return list(self.entradas.values())[0] if self.entradas else None

    def apply(self):
        self.resultado = {k: e.get().strip() for k, e in self.entradas.items()}


def pedir_formulario(parent, titulo, campos, ayuda=None):
    d = FormularioDialogo(parent, titulo, campos, ayuda)
    return d.resultado


def fecha_valida(s):
    if not s:
        return True
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def fecha_es(iso):
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def periodo_texto_individual(fecha_desde, fecha_hasta, fecha_corte_oficial):
    desde = date.fromisoformat(fecha_desde)
    hasta = date.fromisoformat(fecha_hasta) if fecha_hasta else fecha_corte_oficial
    if hasta > fecha_corte_oficial:
        hasta = fecha_corte_oficial
    dias = (hasta - desde).days + 1
    return texto_antiguedad(dias) if dias > 0 else "-"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Antigüedad y Ascensos de Grado — Decreto 1421/02")
        self.geometry("1250x740")
        self.configure(bg=COLOR_BG)

        self.n_doc_actual = None
        self.usuario = None
        self.fecha_corte_oficial = ops.obtener_fecha_corte_oficial()

        self._armar_estilos()
        self._pedir_usuario()
        self._armar_menu()
        self._armar_layout()
        self._refrescar_resumen()

    def _armar_estilos(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=FONT_BASE, background=COLOR_BG)
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabelframe", background=COLOR_BG, font=FONT_SECCION)
        style.configure("TLabelframe.Label", background=COLOR_BG, foreground=COLOR_HEADER, font=FONT_SECCION)
        style.configure("TNotebook", background=COLOR_BG)
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=(14, 6))
        style.configure("Treeview", rowheight=24, font=FONT_BASE, fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background=COLOR_HEADER, foreground="white")
        style.map("Treeview.Heading", background=[("active", COLOR_HEADER)])
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", padding=5)

    def _pedir_usuario(self):
        guardado = usuario_local.leer_usuario_guardado()
        if guardado:
            self.usuario = self._dialogo_bienvenida(guardado)
        if not self.usuario:
            self._pedir_usuario_nuevo()

    def _dialogo_bienvenida(self, nombre_guardado):
        resultado = {"usuario": None}
        win = tk.Toplevel(self)
        win.title("Bienvenido")
        win.configure(bg=COLOR_BG)
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        tk.Label(win, text=f"Hola, {nombre_guardado}. ¡Bienvenido/a!", font=("Segoe UI", 12, "bold"),
                 bg=COLOR_BG, fg=COLOR_HEADER).pack(padx=30, pady=(20, 12))

        def ingresar():
            resultado["usuario"] = nombre_guardado
            win.destroy()

        def cambiar():
            win.destroy()
            self._pedir_usuario_nuevo()
            resultado["usuario"] = self.usuario

        botones = tk.Frame(win, bg=COLOR_BG)
        botones.pack(pady=(0, 20))
        ttk.Button(botones, text="Ingresar", command=ingresar).pack(side="left", padx=8)
        ttk.Button(botones, text="Cambiar usuario", command=cambiar).pack(side="left", padx=8)
        win.protocol("WM_DELETE_WINDOW", ingresar)
        self.wait_window(win)
        return resultado["usuario"]

    def _pedir_usuario_nuevo(self):
        while not self.usuario:
            nombre = simpledialog.askstring(
                "Identificación",
                "Ingresá tu nombre (queda registrado en cada cambio que hagas.\n"
                "Se va a recordar en esta PC para la próxima vez):",
                parent=self)
            if nombre is not None:
                nombre = nombre.strip()
            if nombre:
                self.usuario = nombre
                usuario_local.guardar_usuario(nombre)
            else:
                if not messagebox.askretrycancel("Falta el nombre", "Es necesario ingresar un nombre para continuar."):
                    self.destroy()
                    raise SystemExit

    def _armar_menu(self):
        menubar = tk.Menu(self)
        m_archivo = tk.Menu(menubar, tearoff=0)
        m_archivo.add_command(label="Backup manual ahora", command=self.accion_backup_manual)
        m_archivo.add_command(label="Verificar integridad de la base", command=self.accion_verificar_integridad)
        m_archivo.add_separator()
        m_archivo.add_command(label="Cambiar fecha de corte...", command=self.accion_cambiar_fecha_corte)
        m_archivo.add_command(label="Volver a fecha de corte automática (31/12 del año actual)",
                               command=self.accion_fecha_corte_automatica)
        m_archivo.add_separator()
        m_archivo.add_command(label="Cambiar de usuario...", command=self.accion_cambiar_usuario)
        m_archivo.add_separator()
        m_archivo.add_command(label="Recalcular reglas automáticas (Nivel A/B y tipo de período)...",
                               command=self.accion_recalcular_reglas)
        m_archivo.add_separator()
        m_archivo.add_command(label="Salir", command=self.destroy)
        menubar.add_cascade(label="Sistema", menu=m_archivo)
        self.config(menu=menubar)

    def _armar_layout(self):
        top = tk.Frame(self, bg=COLOR_HEADER, height=34)
        top.pack(fill="x", side="top")
        tk.Label(top, text="  Sistema de Antigüedad y Ascensos — Decreto 1421/02", bg=COLOR_HEADER, fg="white",
                 font=("Segoe UI", 11, "bold")).pack(side="left", pady=6)
        self.lbl_fecha_corte_header = tk.Label(
            top, text=f"Fecha de corte: {fecha_es(self.fecha_corte_oficial.isoformat())}  ",
            bg=COLOR_HEADER, fg="#CFE8EE", font=("Segoe UI", 9))
        self.lbl_fecha_corte_header.pack(side="right", pady=6)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_agentes = ttk.Frame(notebook)
        self.tab_ascensos = ttk.Frame(notebook)
        notebook.add(self.tab_agentes, text="  Agentes  ")
        notebook.add(self.tab_ascensos, text="  Ascensos por año  ")

        self.status = tk.StringVar(value="")
        tk.Label(self, textvariable=self.status, anchor="w", relief="sunken",
                 bg="#E4E7EB", fg="#333").pack(fill="x", side="bottom")

        self._armar_tab_agentes(self.tab_agentes)
        self._armar_tab_ascensos(self.tab_ascensos)

    def set_status(self, msg):
        self.status.set(msg)

    def _armar_tab_agentes(self, frame):
        izq = ttk.Frame(frame)
        izq.pack(side="left", fill="y", padx=(0, 10))

        buscador = ttk.Frame(izq)
        buscador.pack(fill="x", pady=4)
        ttk.Label(buscador, text="Buscar (apellido o documento):").pack(anchor="w")
        self.entry_buscar = ttk.Entry(buscador, width=28)
        self.entry_buscar.pack(side="left", pady=4)
        self.entry_buscar.bind("<Return>", lambda e: self.accion_buscar())
        ttk.Button(buscador, text="Buscar", command=self.accion_buscar).pack(side="left", padx=4)
        ttk.Button(buscador, text="Mostrar todos", command=self.accion_limpiar_busqueda).pack(side="left")

        self.var_incluir_baja = tk.BooleanVar(value=False)
        ttk.Checkbutton(izq, text="Incluir dados de baja (para reactivar)",
                         variable=self.var_incluir_baja,
                         command=self.accion_toggle_incluir_baja).pack(anchor="w", pady=(0, 4))

        cols = ("doc", "nombre")
        self.tree_agentes = ttk.Treeview(izq, columns=cols, show="headings", height=27, selectmode="browse")
        self.tree_agentes.heading("doc", text="Documento")
        self.tree_agentes.heading("nombre", text="Apellido y Nombre")
        self.tree_agentes.column("doc", width=85)
        self.tree_agentes.column("nombre", width=225)
        self.tree_agentes.tag_configure("baja", foreground="#B00020")
        self.tree_agentes.pack(fill="y", expand=True)
        self.tree_agentes.bind("<<TreeviewSelect>>", self.accion_seleccionar_agente)

        ttk.Button(izq, text="+ Crear agente nuevo", command=self.accion_crear_agente).pack(fill="x", pady=(8, 0))
        self.lbl_total_activos = tk.Label(izq, text="", bg=COLOR_BG, fg=COLOR_HEADER,
                                           font=("Segoe UI", 10, "bold"))
        self.lbl_total_activos.pack(anchor="w", pady=(10, 2))
        ttk.Button(izq, text="Exportar listado a Excel", command=self.accion_exportar_agentes).pack(fill="x")
        self.accion_buscar(inicial=True)
        self._actualizar_total_activos()

        der_scroll = tk.Frame(frame, bg=COLOR_BG)
        der_scroll.pack(side="left", fill="both", expand=True)
        der = ttk.Frame(der_scroll)
        der.pack(fill="both", expand=True)

        cab = tk.Frame(der, bg=COLOR_BG)
        cab.pack(fill="x", pady=(2, 6))
        self.lbl_ficha_titulo = tk.Label(cab, text="Seleccioná un agente de la lista",
                                          font=FONT_TITULO, fg=COLOR_HEADER, bg=COLOR_BG, anchor="w")
        self.lbl_ficha_titulo.pack(anchor="w")
        self.lbl_ficha_sub = tk.Label(cab, text="", justify="left", anchor="w", bg=COLOR_BG, font=FONT_BASE)
        self.lbl_ficha_sub.pack(anchor="w")
        self.lbl_ficha_sub2 = tk.Label(cab, text="", justify="left", anchor="w", bg=COLOR_BG, font=FONT_BASE, fg="#555")
        self.lbl_ficha_sub2.pack(anchor="w")
        fila_cab_botones = tk.Frame(cab, bg=COLOR_BG)
        fila_cab_botones.pack(anchor="w", pady=(4, 0))
        ttk.Button(fila_cab_botones, text="Editar Nombre / Nivel / Grado / Dependencia",
                   command=self.accion_editar_agente).pack(side="left")
        self.btn_dar_baja = ttk.Button(fila_cab_botones, text="Dar de baja...", command=self.accion_dar_de_baja)
        self.btn_dar_baja.pack(side="left", padx=(6, 0))
        self.btn_reactivar = ttk.Button(fila_cab_botones, text="Reactivar", command=self.accion_reactivar)
        self.btn_reactivar.pack(side="left", padx=(6, 0))

        fila2 = tk.Frame(der, bg=COLOR_BG)
        fila2.pack(fill="x", pady=4)

        tit_frame = ttk.LabelFrame(fila2, text="Título de grado (universitario)")
        tit_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.lbl_titulos = tk.Label(tit_frame, text="", justify="left", anchor="w", bg=COLOR_BG, wraplength=340)
        self.lbl_titulos.pack(anchor="w", padx=6, pady=(6, 2))
        fila_tit_botones = tk.Frame(tit_frame, bg=COLOR_BG)
        fila_tit_botones.pack(anchor="w", padx=6, pady=(0, 6))
        ttk.Button(fila_tit_botones, text="Editar título",
                   command=self.accion_editar_titulo).pack(side="left")
        ttk.Button(fila_tit_botones, text="Contar grado desde la fecha de titulación",
                   command=self.accion_usar_fecha_titulacion).pack(side="left", padx=6)

        cfg_frame = ttk.LabelFrame(fila2, text="¿Desde cuándo se cuenta el grado?")
        cfg_frame.pack(side="left", fill="both", expand=True, padx=(4, 0))
        tk.Label(cfg_frame,
                 text="Por defecto, el sistema cuenta desde la fecha de cada período de "
                      "antigüedad marcado 'Sí' en la tabla de abajo. Acá se puede forzar "
                      "otra fecha de inicio o un tope, sólo para este agente. (Para Nivel "
                      "A y B, si no se configura nada, se usa automáticamente la fecha de "
                      "titulación.)",
                 justify="left", anchor="w", bg=COLOR_BG, fg="#666", font=("Segoe UI", 8),
                 wraplength=300).pack(anchor="w", padx=6, pady=(6, 2), fill="x")
        self.lbl_config = tk.Label(cfg_frame, text="", justify="left", anchor="w", bg=COLOR_BG)
        self.lbl_config.pack(anchor="w", padx=6, pady=(0, 4))
        ttk.Button(cfg_frame, text="Configurar fechas / grado base", command=self.accion_configurar_agente).pack(anchor="w", padx=6, pady=(0, 6))

        per_frame = ttk.LabelFrame(der, text="Períodos de antigüedad")
        per_frame.pack(fill="both", expand=True, pady=4)

        cols_p = ("desde", "hasta", "duracion", "organismo", "tipo", "c1421", "capn")
        self.tree_periodos = ttk.Treeview(per_frame, columns=cols_p, show="headings", height=6)
        anchos = {"desde": 85, "hasta": 85, "duracion": 140, "organismo": 260, "tipo": 70,
                  "c1421": 75, "capn": 75}
        titulos_p = {"desde": "Desde", "hasta": "Hasta", "duracion": "Duración", "organismo": "Organismo",
                     "tipo": "Tipo", "c1421": "¿Grado 1421?", "capn": "¿APN?"}
        for c in cols_p:
            self.tree_periodos.heading(c, text=titulos_p[c])
            self.tree_periodos.column(c, width=anchos[c])
        self.tree_periodos.tag_configure("si1421", background="#E7F5EA")
        self.tree_periodos.tag_configure("no1421", background="#F5F5F5")
        self.tree_periodos.pack(fill="both", expand=True, padx=6, pady=4)
        self.tree_periodos.bind("<<TreeviewSelect>>", self.accion_mostrar_observaciones)

        self.lbl_observaciones = tk.Label(per_frame, text="", justify="left", anchor="w", bg=COLOR_BG,
                                           fg="#555", font=("Segoe UI", 8), wraplength=900)
        self.lbl_observaciones.pack(anchor="w", padx=6, pady=(0, 4), fill="x")

        botones_periodos = ttk.Frame(per_frame)
        botones_periodos.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(botones_periodos, text="Cargar período nuevo", command=self.accion_cargar_periodo).pack(side="left")
        ttk.Button(botones_periodos, text="Modificar seleccionado", command=self.accion_modificar_periodo).pack(side="left", padx=4)
        ttk.Button(botones_periodos, text="Alternar Cuenta/No cuenta (grado 1421)", command=self.accion_toggle_cuenta).pack(side="left", padx=4)
        ttk.Button(botones_periodos, text="Desactivar seleccionado", command=self.accion_desactivar_periodo).pack(side="left", padx=4)
        ttk.Button(botones_periodos, text="Cortar por una licencia...", command=self.accion_cortar_periodo).pack(side="left", padx=4)

        totales = tk.Frame(der, bg=COLOR_BG)
        totales.pack(fill="x", pady=(6, 2))

        box_apn = tk.Frame(totales, bg=COLOR_BOX_APN, bd=1, relief="solid")
        box_apn.pack(side="left", fill="both", expand=True, padx=(0, 4), ipady=8)
        tk.Label(box_apn, text="Antigüedad en la Administración Pública Nacional", bg=COLOR_BOX_APN,
                 font=FONT_TOTAL_LABEL, wraplength=260).pack(anchor="w", padx=10)
        self.lbl_total_apn = tk.Label(box_apn, text="—", bg=COLOR_BOX_APN, font=FONT_TOTAL_VALOR, fg="#333")
        self.lbl_total_apn.pack(anchor="w", padx=10)

        box_1421 = tk.Frame(totales, bg=COLOR_BOX_1421, bd=1, relief="solid")
        box_1421.pack(side="left", fill="both", expand=True, padx=(4, 0), ipady=8)
        tk.Label(box_1421, text="Antigüedad para ascenso de grado — Decreto 1421/02", bg=COLOR_BOX_1421,
                 font=FONT_TOTAL_LABEL, wraplength=260).pack(anchor="w", padx=10)
        self.lbl_total_1421 = tk.Label(box_1421, text="—", bg=COLOR_BOX_1421, font=FONT_TOTAL_VALOR, fg=COLOR_HEADER)
        self.lbl_total_1421.pack(anchor="w", padx=10)

        self.lbl_totales_fecha = tk.Label(der, text="", bg=COLOR_BG, fg="#777", font=("Segoe UI", 8))
        self.lbl_totales_fecha.pack(anchor="w", pady=(2, 0))

        proy_frame = tk.Frame(der, bg=COLOR_BG)
        proy_frame.pack(anchor="w", fill="x", pady=(6, 0))
        tk.Label(proy_frame, text="Proyectar antigüedad a otra fecha (AAAA-MM-DD):",
                 bg=COLOR_BG).pack(side="left")
        self.entry_proyeccion = ttk.Entry(proy_frame, width=12)
        self.entry_proyeccion.pack(side="left", padx=(4, 4))
        self.entry_proyeccion.bind("<Return>", lambda e: self.accion_proyectar_fecha())
        ttk.Button(proy_frame, text="Calcular", command=self.accion_proyectar_fecha).pack(side="left")

        self.lbl_proyeccion = tk.Label(der, text="", justify="left", anchor="w", bg=COLOR_BG,
                                        fg=COLOR_HEADER, font=("Segoe UI", 9, "bold"), wraplength=560)
        self.lbl_proyeccion.pack(anchor="w", fill="x", pady=(4, 0))

    def accion_buscar(self, inicial=False):
        texto = self.entry_buscar.get().strip()
        if not texto and not inicial:
            messagebox.showinfo("Buscar", "Escribí un apellido o número de documento para buscar.")
            return
        incluir_baja = self.var_incluir_baja.get()
        # Con el casillero tildado el universo es más grande (vinculados +
        # dados de baja, ~387 hoy) que sin él (sólo los que cuentan, ~241) --
        # el límite de "mostrar todos" tiene que cubrir ese universo más
        # grande para no cortar resultados en silencio.
        if inicial:
            limite = 500 if incluir_baja else 250
        else:
            limite = 200 if incluir_baja else 100
        resultados = ops.buscar_agentes(texto, incluir_inactivos=True, solo_1421=True,
                                         limite=limite, incluir_dados_de_baja=incluir_baja)
        self.tree_agentes.delete(*self.tree_agentes.get_children())
        for a in sorted(resultados, key=lambda x: x["apellido_nombre"]):
            tags = ("baja",) if not a["activo"] else ()
            self.tree_agentes.insert("", "end", iid=str(a["n_doc"]), values=(a["n_doc"], a["apellido_nombre"]),
                                      tags=tags)
        extra = " (incluye dados de baja)" if incluir_baja else ""
        self.set_status(f"{len(resultados)} agente(s) del Decreto 1421/02 mostrados{extra}.")

    def accion_toggle_incluir_baja(self):
        """Al tildar/destildar el casillero se repite la búsqueda sola, sin
        esperar a que se apriete "Buscar" de nuevo. Si el buscador está
        vacío, se comporta como "Mostrar todos" (no pide que se escriba
        algo) -- así se puede ver a todos los dados de baja aunque no te
        acuerdes el nombre exacto de la persona."""
        texto = self.entry_buscar.get().strip()
        self.accion_buscar(inicial=not texto)

    def accion_limpiar_busqueda(self):
        self.entry_buscar.delete(0, "end")
        self.accion_buscar(inicial=True)

    def _actualizar_total_activos(self):
        total = ops.contar_agentes_activos()
        self.lbl_total_activos.config(text=f"Total contratados activos: {total}")

    def accion_exportar_agentes(self):
        try:
            destino = exportar.exportar_agentes_excel()
            messagebox.showinfo("Exportado", f"Archivo generado:\n{destino}")
        except Exception as e:
            messagebox.showerror("Error al exportar", str(e))

    def accion_mostrar_observaciones(self, event=None):
        sel = self.tree_periodos.selection()
        if not sel:
            return
        obs = self._observaciones_periodos.get(sel[0], "")
        self.lbl_observaciones.config(text=f"Observaciones: {obs}")

    def accion_seleccionar_agente(self, event=None):
        sel = self.tree_agentes.selection()
        if not sel:
            return
        n_doc = int(sel[0])
        self.n_doc_actual = n_doc
        self._cargar_ficha(n_doc)

    def _cargar_ficha(self, n_doc):
        a = ops.obtener_agente(n_doc)
        if not a:
            return

        estado = "Activo" if a["activo"] else "INACTIVO (dado de baja)"
        nivel_grado = f"{a['nivel_actual'] or '?'}-{a['grado_actual'] if a['grado_actual'] is not None else '?'}"
        self.lbl_ficha_titulo.config(text=f"{a['apellido_nombre']}")
        self.lbl_ficha_sub.config(
            text=f"Documento: {a['n_doc']}     Nivel y Grado: {nivel_grado}     Estado: {estado}",
            fg="#333" if a["activo"] else "#B00020")
        if a["activo"]:
            self.btn_dar_baja.state(["!disabled"])
            self.btn_reactivar.state(["disabled"])
        else:
            self.btn_dar_baja.state(["disabled"])
            self.btn_reactivar.state(["!disabled"])
        dependencia = a.get("dependencia_1421") or "-"
        self.lbl_ficha_sub2.config(text=f"Dependencia: {dependencia}")

        cfg = a["config"] or {}
        self.lbl_config.config(
            text=f"Fecha inicio de conteo (override): {fecha_es(cfg.get('fecha_inicio_conteo_grado')) or '(usa fecha de los períodos)'}\n"
                 f"Fecha de cierre de conteo: {fecha_es(cfg.get('fecha_cierre_conteo')) or '(sin cierre)'}\n"
                 f"Grado base de partida: {cfg.get('grado_base', 0)}")

        self.tree_periodos.delete(*self.tree_periodos.get_children())
        self._observaciones_periodos = {}
        for p in a["periodos"]:
            dur = periodo_texto_individual(p["fecha_desde"], p["fecha_hasta"], self.fecha_corte_oficial)
            c1421 = "SI" if p["cuenta_ascenso"] else "NO"
            capn = "SI" if p.get("suma_apn", 1) else "NO"
            tag = "si1421" if p["cuenta_ascenso"] else "no1421"
            self._observaciones_periodos[str(p["id"])] = p.get("observaciones") or "(sin observaciones)"
            self.tree_periodos.insert("", "end", iid=str(p["id"]), tags=(tag,), values=(
                fecha_es(p["fecha_desde"]), fecha_es(p["fecha_hasta"]) or "vigente", dur,
                p["organismo"] or "", p.get("tipo_prestacion") or "", c1421, capn))
        self.lbl_observaciones.config(text="Observaciones: (seleccioná un período de la tabla para verlas)")

        if a["titulos_grado"]:
            txt = "\n".join(f"{t['titulo'] or '(sin especificar)'}\nTitulación: {fecha_es(t['fecha_titulacion']) or 'sin fecha'}"
                             for t in a["titulos_grado"])
        else:
            txt = "No registra título de grado universitario."
        self.lbl_titulos.config(text=txt)

        calc = ops.calcular_antiguedad_agente(n_doc, self.fecha_corte_oficial)
        self.lbl_total_apn.config(text=calc["antiguedad_apn_texto"])
        self.lbl_total_1421.config(text=calc["antiguedad_texto"])
        self.lbl_totales_fecha.config(text=f"Calculado al {fecha_es(self.fecha_corte_oficial.isoformat())}.")

        # Limpiar la proyección de fecha: es una consulta puntual que no debe
        # quedar pegada al pasar de un agente a otro.
        self.entry_proyeccion.delete(0, "end")
        self.lbl_proyeccion.config(text="")

    def _requiere_agente(self):
        if not self.n_doc_actual:
            messagebox.showwarning("Sin selección", "Primero elegí un agente de la lista.")
            return False
        return True

    def accion_cargar_periodo(self):
        if not self._requiere_agente():
            return
        r = pedir_formulario(
            self, "Cargar período de antigüedad",
            [("fecha_desde", "Fecha desde (AAAA-MM-DD):", ""),
             ("fecha_hasta", "Fecha hasta (vacío = vigente):", ""),
             ("organismo", "Organismo / dependencia:", ""),
             ("cuenta", "¿Cuenta para ascenso de grado 1421? (S/N):", "S"),
             ("tipo", "Tipo (texto libre, opcional):", ""),
             ("capn", "¿Cuenta para Antigüedad APN? (S/N):", "S"),
             ("observaciones", "Observaciones:", "")],
            ayuda="Dejá 'Fecha hasta' vacía si el período sigue vigente."
        )
        if r is None:
            return
        if not fecha_valida(r["fecha_desde"]) or not r["fecha_desde"]:
            messagebox.showerror("Error", "La fecha desde es obligatoria y debe tener formato AAAA-MM-DD.")
            return
        if not fecha_valida(r["fecha_hasta"]):
            messagebox.showerror("Error", "La fecha hasta debe tener formato AAAA-MM-DD (o vacía).")
            return
        cuenta = r["cuenta"].strip().upper() in ("S", "SI", "SÍ", "1")
        capn = r["capn"].strip().upper() in ("S", "SI", "SÍ", "1")
        try:
            ops.cargar_periodo(self.n_doc_actual, r["fecha_desde"], r["fecha_hasta"] or None,
                                r["organismo"], cuenta, r["observaciones"], self.usuario,
                                tipo_prestacion=r["tipo"] or None, suma_apn=capn)
            self._cargar_ficha(self.n_doc_actual)
            self.set_status("Período cargado correctamente. Se hizo backup automático antes de guardar.")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def _periodo_seleccionado(self):
        sel = self.tree_periodos.selection()
        if not sel:
            messagebox.showwarning("Sin selección", "Seleccioná un período de la tabla primero.")
            return None
        return int(sel[0])

    def accion_modificar_periodo(self):
        pid = self._periodo_seleccionado()
        if pid is None:
            return
        vals = self.tree_periodos.item(str(pid))["values"]
        desde, hasta = vals[0], vals[1]
        organismo, tipo, c1421, capn = vals[3], vals[4], vals[5], vals[6]
        hasta = "" if hasta == "vigente" else hasta
        # Observación actual real (self._observaciones_periodos guarda un texto de
        # relleno "(sin observaciones)" para mostrar en pantalla cuando está vacía,
        # así que hay que traerla de nuevo tal cual está en la base para precargar
        # el formulario -- si no, nunca se puede saber qué había ni borrarlo bien).
        obs_actual = self._observaciones_periodos.get(str(pid), "")
        if obs_actual == "(sin observaciones)":
            obs_actual = ""

        def a_iso(d):
            if not d:
                return ""
            try:
                return datetime.strptime(d, "%d/%m/%Y").date().isoformat()
            except ValueError:
                return d
        r = pedir_formulario(
            self, f"Modificar período #{pid}",
            [("fecha_desde", "Fecha desde:", a_iso(desde)),
             ("fecha_hasta", "Fecha hasta (vacío = vigente):", a_iso(hasta)),
             ("organismo", "Organismo:", organismo),
             ("cuenta", "¿Cuenta para ascenso de grado 1421? (S/N):", "S" if c1421 == "SI" else "N"),
             ("tipo", "Tipo (texto libre, opcional):", tipo or ""),
             ("capn", "¿Cuenta para Antigüedad APN? (S/N):", "S" if capn == "SI" else "N"),
             ("observaciones", "Observaciones:", obs_actual)],
            ayuda="El campo Observaciones reemplaza el texto anterior por completo "
                  "(dejalo vacío para borrarlo)."
        )
        if r is None:
            return
        if not fecha_valida(r["fecha_desde"]) or not fecha_valida(r["fecha_hasta"]):
            messagebox.showerror("Error", "Formato de fecha inválido. Usar AAAA-MM-DD.")
            return
        cambios = {
            "fecha_desde": r["fecha_desde"],
            "fecha_hasta": r["fecha_hasta"] or None,
            "organismo": r["organismo"],
            "cuenta_ascenso": int(r["cuenta"].strip().upper() in ("S", "SI", "SÍ", "1")),
            "tipo_prestacion": r["tipo"] or None,
            "suma_apn": int(r["capn"].strip().upper() in ("S", "SI", "SÍ", "1")),
            "observaciones": r["observaciones"],
        }
        try:
            ops.modificar_periodo(pid, self.usuario, **cambios)
            self._cargar_ficha(self.n_doc_actual)
            self.set_status(f"Período #{pid} modificado. Backup automático realizado antes de guardar.")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def accion_toggle_cuenta(self):
        pid = self._periodo_seleccionado()
        if pid is None:
            return
        vals = self.tree_periodos.item(str(pid))["values"]
        cuenta_actual = vals[5] == "SI"
        nuevo = not cuenta_actual
        if not messagebox.askyesno("Confirmar", f"¿Cambiar el período #{pid} a "
                                    f"{'CUENTA' if nuevo else 'NO CUENTA'} para el ascenso de grado 1421?"):
            return
        try:
            ops.marcar_cuenta_ascenso(pid, nuevo, self.usuario)
            self._cargar_ficha(self.n_doc_actual)
            self.set_status(f"Período #{pid} actualizado.")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def accion_desactivar_periodo(self):
        pid = self._periodo_seleccionado()
        if pid is None:
            return
        motivo = simpledialog.askstring("Motivo", "¿Por qué se desactiva este período?\n"
                                         "(no se borra, queda en el historial)", parent=self)
        if motivo is None:
            return
        try:
            ops.desactivar_periodo(pid, self.usuario, motivo)
            self._cargar_ficha(self.n_doc_actual)
            self.set_status(f"Período #{pid} desactivado (sigue en el historial).")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def accion_cortar_periodo(self):
        """Divide el período seleccionado en tramos, dejando la licencia
        (licencia sin goce, excedencia, etc.) como una fila propia y
        visible en la tabla -- no como un hueco invisible. No cambia el
        cálculo de antigüedad: la fila de la licencia queda marcada para
        que no cuente."""
        pid = self._periodo_seleccionado()
        if pid is None:
            return
        r = pedir_formulario(
            self, f"Cortar período #{pid} por una licencia",
            [("desde", "Licencia desde (AAAA-MM-DD):", ""),
             ("hasta", "Licencia hasta (AAAA-MM-DD):", ""),
             ("motivo", "Motivo (ej. licencia extraordinaria sin goce, excedencia):", ""),
             ("capn", "¿La licencia cuenta para Antigüedad APN? (S/N):", "N")],
            ayuda="La licencia queda como una fila propia en la tabla, con ¿Grado 1421? = NO "
                  "siempre. El período se acorta hasta el día anterior a la licencia, y se crea "
                  "uno nuevo desde el día siguiente hasta donde llegaba el original."
        )
        if r is None:
            return
        if not fecha_valida(r["desde"]) or not r["desde"] or not fecha_valida(r["hasta"]) or not r["hasta"]:
            messagebox.showerror("Error", "Las dos fechas de la licencia son obligatorias, formato AAAA-MM-DD.")
            return
        capn_licencia = r["capn"].strip().upper() in ("S", "SI", "SÍ", "1")
        try:
            _, licencia_id, nuevo_id = ops.cortar_periodo_por_licencia(
                pid, r["desde"], r["hasta"], self.usuario, r["motivo"], suma_apn_licencia=capn_licencia)
            self._cargar_ficha(self.n_doc_actual)
            if nuevo_id:
                self.set_status(f"Período #{pid} cortado: licencia #{licencia_id} registrada, "
                                 f"continúa en el período #{nuevo_id}.")
            else:
                self.set_status(f"Período #{pid} acortado; licencia #{licencia_id} registrada hasta el final.")
        except Exception as e:
            messagebox.showerror("Error al cortar el período", str(e))

    def accion_configurar_agente(self):
        if not self._requiere_agente():
            return
        a = ops.obtener_agente(self.n_doc_actual)
        cfg = a["config"] or {}
        r = pedir_formulario(
            self, "Configuración de cómputo de grado",
            [("inicio", "Fecha desde la que se cuenta el grado (override):", cfg.get("fecha_inicio_conteo_grado") or ""),
             ("cierre", "Fecha de cierre de cómputo:", cfg.get("fecha_cierre_conteo") or ""),
             ("grado_base", "Grado base de partida:", str(cfg.get("grado_base", 0) or 0)),
             ("observaciones", "Observaciones:", cfg.get("observaciones") or "")],
            ayuda="Formato de fechas: AAAA-MM-DD. Dejá vacío lo que quieras que se calcule automáticamente."
        )
        if r is None:
            return
        if not fecha_valida(r["inicio"]) or not fecha_valida(r["cierre"]):
            messagebox.showerror("Error", "Formato de fecha inválido. Usar AAAA-MM-DD.")
            return
        try:
            grado_base = int(r["grado_base"]) if r["grado_base"] else 0
        except ValueError:
            messagebox.showerror("Error", "El grado base debe ser un número.")
            return
        try:
            ops.set_config_agente(self.n_doc_actual, self.usuario,
                                   fecha_inicio_conteo_grado=r["inicio"] or "",
                                   fecha_cierre_conteo=r["cierre"] or "",
                                   grado_base=grado_base, observaciones=r["observaciones"])
            self._cargar_ficha(self.n_doc_actual)
            self.set_status("Configuración guardada.")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def accion_proyectar_fecha(self):
        """Consulta puntual: antigüedad y ascenso de UN agente a cualquier fecha
        (pasada o futura), sin cambiar la fecha de corte general ni la
        configuración guardada de nadie. Reutiliza el mismo cálculo que ya
        usa 'Ascensos por año'. El resultado se muestra en self.lbl_proyeccion,
        que se limpia solo cada vez que se carga otra ficha (_cargar_ficha)."""
        if not self._requiere_agente():
            return
        fecha_txt = self.entry_proyeccion.get().strip()
        if not fecha_txt:
            messagebox.showerror("Error", "Escribí una fecha (AAAA-MM-DD) para proyectar.")
            return
        if not fecha_valida(fecha_txt):
            messagebox.showerror("Error", "Formato de fecha inválido. Usar AAAA-MM-DD.")
            return
        fecha = date.fromisoformat(fecha_txt)
        calc = ops.calcular_antiguedad_agente(self.n_doc_actual, fecha)
        r = ops.evaluar_ascenso_agente(self.n_doc_actual, fecha.year, fecha_corte=fecha)

        if r["asciende"]:
            resultado_grado = f"Asciende, con efecto a partir del {fecha_es(r['fecha_efectiva_ascenso'])}."
        else:
            resultado_grado = "No suma un grado nuevo en esta evaluación."

        self.lbl_proyeccion.config(
            text=f"Proyección al {fecha_es(fecha_txt)} — "
                 f"1421: {calc['antiguedad_texto']} (grados: {r['grados_acumulados']})  |  "
                 f"APN: {calc['antiguedad_apn_texto']}  |  {resultado_grado}"
        )

    def accion_editar_agente(self):
        if not self._requiere_agente():
            return
        a = ops.obtener_agente(self.n_doc_actual)
        r = pedir_formulario(
            self, "Editar Nombre / Nivel / Grado / Dependencia",
            [("nombre", "Apellido y Nombre:", a["apellido_nombre"] or ""),
             ("nivel", "Nivel (A-F):", a["nivel_actual"] or ""),
             ("grado", "Grado:", str(a["grado_actual"]) if a["grado_actual"] is not None else ""),
             ("dependencia", "Dependencia:", a.get("dependencia_1421") or "")],
            ayuda="Estos son los datos informativos que se muestran en la ficha. "
                  "El Documento (DNI) no se puede editar acá: es la clave con la que "
                  "está enganchado todo el historial del agente."
        )
        if r is None:
            return
        if not r["nombre"].strip():
            messagebox.showerror("Error", "El apellido y nombre no puede quedar vacío.")
            return
        grado = None
        if r["grado"]:
            try:
                grado = int(r["grado"])
            except ValueError:
                messagebox.showerror("Error", "El grado debe ser un número.")
                return
        try:
            ops.editar_datos_agente(self.n_doc_actual, self.usuario, apellido_nombre=r["nombre"],
                                     nivel_actual=r["nivel"] or "",
                                     grado_actual=grado, dependencia_1421=r["dependencia"] or "")
            aplicado = ops.aplicar_default_titulacion_ab(self.n_doc_actual, self.usuario)
            self._cargar_ficha(self.n_doc_actual)
            if aplicado:
                self.set_status("Datos del agente actualizados. Al ser Nivel A/B, se fijó automáticamente "
                                 "la fecha de titulación como inicio de cómputo de grado.")
            else:
                self.set_status("Datos del agente actualizados.")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def accion_dar_de_baja(self):
        if not self._requiere_agente():
            return
        nombre = self.lbl_ficha_titulo.cget("text")
        if not messagebox.askyesno(
                "Dar de baja",
                f"¿Dar de baja a {nombre}?\n\n"
                "No se borra nada: queda desactivado y deja de aparecer en búsquedas, "
                "\"Ascensos por año\", el total de contratados activos y el Excel exportado. "
                "Todo su historial (períodos, títulos) sigue intacto, y se puede reactivar "
                "en cualquier momento."):
            return
        motivo = simpledialog.askstring(
            "Motivo de la baja", "¿Por qué se da de baja? (ej. Renuncia, Cese)", parent=self)
        if motivo is None:
            return
        try:
            ops.dar_de_baja_agente(self.n_doc_actual, self.usuario, motivo)
            self._cargar_ficha(self.n_doc_actual)
            self._actualizar_total_activos()
            self.set_status(f"{nombre} dado de baja. Sigue en la base, se puede reactivar cuando haga falta.")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def accion_reactivar(self):
        if not self._requiere_agente():
            return
        nombre = self.lbl_ficha_titulo.cget("text")
        motivo = simpledialog.askstring(
            "Motivo de la reactivación", "¿Por qué se reactiva? (opcional)", parent=self)
        if motivo is None:
            return
        try:
            ops.reactivar_agente(self.n_doc_actual, self.usuario, motivo)
            self._cargar_ficha(self.n_doc_actual)
            self._actualizar_total_activos()
            self.set_status(f"{nombre} reactivado.")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def accion_editar_titulo(self):
        if not self._requiere_agente():
            return
        a = ops.obtener_agente(self.n_doc_actual)
        actual = a["titulos_grado"][0] if a["titulos_grado"] else {}
        r = pedir_formulario(
            self, "Editar título de grado",
            [("titulo", "Título:", actual.get("titulo") or ""),
             ("institucion", "Institución:", actual.get("institucion") or ""),
             ("fecha_titulacion", "Fecha de titulación (AAAA-MM-DD):", actual.get("fecha_titulacion") or ""),
             ("fecha_egreso", "Fecha de egreso (AAAA-MM-DD):", actual.get("fecha_egreso") or "")],
        )
        if r is None:
            return
        if not fecha_valida(r["fecha_titulacion"]) or not fecha_valida(r["fecha_egreso"]):
            messagebox.showerror("Error", "Formato de fecha inválido. Usar AAAA-MM-DD.")
            return
        try:
            ops.editar_titulo_grado(self.n_doc_actual, self.usuario, titulo=r["titulo"],
                                     institucion=r["institucion"], fecha_titulacion=r["fecha_titulacion"] or None,
                                     fecha_egreso=r["fecha_egreso"] or None)
            aplicado = ops.aplicar_default_titulacion_ab(self.n_doc_actual, self.usuario)
            self._cargar_ficha(self.n_doc_actual)
            if aplicado:
                self.set_status("Título actualizado. Al ser Nivel A/B, se fijó automáticamente la fecha "
                                 "de titulación como inicio de cómputo de grado.")
            else:
                self.set_status("Título actualizado.")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def accion_usar_fecha_titulacion(self):
        if not self._requiere_agente():
            return
        a = ops.obtener_agente(self.n_doc_actual)
        if not a["titulos_grado"] or not a["titulos_grado"][0].get("fecha_titulacion"):
            messagebox.showwarning("Sin fecha de titulación",
                                    "Este agente no tiene una fecha de titulación cargada todavía.\n"
                                    "Usá 'Editar título' para cargarla primero.")
            return
        fecha_tit = a["titulos_grado"][0]["fecha_titulacion"]
        if not messagebox.askyesno("Confirmar", f"¿Contar el grado a partir de la fecha de titulación "
                                    f"({fecha_es(fecha_tit)})?\nEsto reemplaza la fecha de inicio de "
                                    f"conteo configurada para este agente."):
            return
        try:
            ops.set_config_agente(self.n_doc_actual, self.usuario, fecha_inicio_conteo_grado=fecha_tit)
            self._cargar_ficha(self.n_doc_actual)
            self.set_status(f"Ahora se cuenta el grado desde la fecha de titulación ({fecha_es(fecha_tit)}).")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def accion_crear_agente(self):
        r = pedir_formulario(
            self, "Crear agente nuevo",
            [("n_doc", "Número de documento:", ""),
             ("nombre", "Apellido y Nombre:", ""),
             ("nivel", "Nivel (A-F, opcional):", ""),
             ("grado", "Grado (opcional):", ""),
             ("dependencia", "Dependencia (opcional):", "")],
            ayuda="Después de crearlo, usá los botones de la ficha para cargar su "
                  "período de antigüedad y su título."
        )
        if r is None:
            return
        if not r["n_doc"].isdigit():
            messagebox.showerror("Error", "El documento debe ser numérico.")
            return
        grado = int(r["grado"]) if r["grado"].isdigit() else None
        n_doc_nuevo = int(r["n_doc"])
        try:
            ops.crear_agente_manual(n_doc_nuevo, r["nombre"], self.usuario,
                                     r["nivel"] or None, grado)
            from db import Transaccion
            with Transaccion(f"marcar_1421_nuevo_{n_doc_nuevo}") as conn:
                conn.execute("UPDATE agentes SET cuenta_1421=1, vinculado_1421=1, "
                             "motivo_clasif_1421='Alta manual directa' WHERE n_doc=?", (n_doc_nuevo,))
            if r["dependencia"]:
                ops.editar_datos_agente(n_doc_nuevo, self.usuario, dependencia_1421=r["dependencia"])
            self.entry_buscar.delete(0, "end")
            self.entry_buscar.insert(0, r["nombre"])
            self.accion_buscar()
            self.update_idletasks()
            if self.tree_agentes.exists(str(n_doc_nuevo)):
                self.tree_agentes.selection_set(str(n_doc_nuevo))
                self.tree_agentes.see(str(n_doc_nuevo))
                self.accion_seleccionar_agente()
            messagebox.showinfo("Listo", "Agente creado correctamente.\n\n"
                                 "Ahora cargá su período de antigüedad ('Cargar período nuevo') "
                                 "y su título ('Editar título') con los botones de la ficha.")
            self._actualizar_total_activos()
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def _armar_tab_ascensos(self, frame):
        top = ttk.Frame(frame)
        top.pack(fill="x", pady=8)
        ttk.Label(top, text="Fecha de corte a evaluar (AAAA-MM-DD):").pack(side="left", padx=(0, 4))
        self.entry_fecha_corte_ascensos = ttk.Entry(top, width=12)
        self.entry_fecha_corte_ascensos.insert(0, f"{self.fecha_corte_oficial.year}-12-31")
        self.entry_fecha_corte_ascensos.pack(side="left")
        ttk.Button(top, text="Calcular ascensos", command=self.accion_calcular_ascensos).pack(side="left", padx=8)
        ttk.Button(top, text="Exportar a Excel", command=self.accion_exportar_excel).pack(side="left")

        self.lbl_ascensos_resumen = tk.Label(frame, text="", font=("Segoe UI", 10, "bold"), bg=COLOR_BG, fg=COLOR_HEADER)
        self.lbl_ascensos_resumen.pack(anchor="w", padx=4)

        cols = ("doc", "nombre", "grado_ant", "grado_nuevo", "suma", "antiguedad", "efectivo")
        self.tree_ascensos = ttk.Treeview(frame, columns=cols, show="headings", height=25)
        titulos = {"doc": "Documento", "nombre": "Apellido y Nombre", "grado_ant": "Grado anterior",
                   "grado_nuevo": "Grado nuevo", "suma": "Suma", "antiguedad": "Antigüedad computable",
                   "efectivo": "Fecha efectiva"}
        anchos = {"doc": 90, "nombre": 260, "grado_ant": 100, "grado_nuevo": 100, "suma": 60,
                  "antiguedad": 220, "efectivo": 110}
        for c in cols:
            self.tree_ascensos.heading(c, text=titulos[c])
            self.tree_ascensos.column(c, width=anchos[c])
        self.tree_ascensos.pack(fill="both", expand=True, padx=4, pady=4)

        self._ultimo_anio_calculado = None
        self._ultima_fecha_corte_calculada = None

    def accion_calcular_ascensos(self):
        fecha_corte_txt = self.entry_fecha_corte_ascensos.get().strip()
        if not fecha_corte_txt or not fecha_valida(fecha_corte_txt):
            messagebox.showerror("Error", "Ingresá una fecha de corte válida, formato AAAA-MM-DD.")
            return
        fecha_corte = date.fromisoformat(fecha_corte_txt)
        anio = fecha_corte.year

        self.set_status(f"Calculando ascensos al {fecha_es(fecha_corte_txt)}... (puede tardar unos segundos)")
        self.update_idletasks()
        resultados = ops.listar_ascensos_anio(anio, fecha_corte=fecha_corte)
        self.tree_ascensos.delete(*self.tree_ascensos.get_children())
        for r in resultados:
            self.tree_ascensos.insert("", "end", values=(
                r["n_doc"], r["apellido_nombre"], r["grados_anio_anterior"], r["grados_acumulados"],
                f"+{r['grados_nuevos']}", r["antiguedad_computable_texto"], fecha_es(r["fecha_efectiva_ascenso"])))
        fecha_efectiva = fecha_corte + timedelta(days=1)
        self.lbl_ascensos_resumen.config(
            text=f"Ascienden {len(resultados)} agente(s) del Decreto 1421/02, "
                 f"con efecto a partir del {fecha_es(fecha_efectiva.isoformat())}.")
        self._ultimo_anio_calculado = anio
        self._ultima_fecha_corte_calculada = fecha_corte
        self.set_status("Cálculo completado.")

    def accion_exportar_excel(self):
        anio = self._ultimo_anio_calculado
        if anio is None:
            messagebox.showinfo("Exportar", "Primero calculá los ascensos de un año.")
            return
        try:
            destino = exportar.exportar_ascensos_excel(anio, fecha_corte=self._ultima_fecha_corte_calculada)
            messagebox.showinfo("Exportado", f"Archivo generado:\n{destino}")
        except Exception as e:
            messagebox.showerror("Error al exportar", str(e))

    def accion_backup_manual(self):
        destino = backup_antes_de_escribir("manual_gui")
        messagebox.showinfo("Backup", f"Copia de seguridad creada:\n{destino}")

    def accion_verificar_integridad(self):
        ok, detalle = verificar_integridad()
        backups = sorted(BACKUP_DIR.glob("*.db"))
        msg = (f"Integridad de la base: {'OK' if ok else 'PROBLEMA DETECTADO'}\n"
               f"Detalle: {detalle}\n\nArchivo: {DB_PATH}\nBackups disponibles: {len(backups)}")
        if ok:
            messagebox.showinfo("Verificación de integridad", msg)
        else:
            messagebox.showerror("Verificación de integridad", msg)

    def accion_cambiar_fecha_corte(self):
        nueva = simpledialog.askstring(
            "Fecha de corte",
            f"Fecha actual: {fecha_es(self.fecha_corte_oficial.isoformat())}\n\n"
            "Ingresá la fecha a la que se debe calcular la antigüedad en todas\n"
            "las fichas (AAAA-MM-DD). Por defecto es automática (31/12 del año\n"
            "actual) y se actualiza sola cada año; esto fija una fecha manual\n"
            "hasta que elijas 'Volver a fecha de corte automática'.",
            parent=self)
        if not nueva:
            return
        if not fecha_valida(nueva):
            messagebox.showerror("Error", "Formato inválido. Usar AAAA-MM-DD.")
            return
        ops.set_fecha_corte_oficial(nueva, self.usuario)
        self.fecha_corte_oficial = ops.obtener_fecha_corte_oficial()
        self._actualizar_encabezado_fecha_corte()
        messagebox.showinfo("Listo", f"Fecha de corte actualizada a {fecha_es(nueva)}.\n"
                             "Volvé a seleccionar un agente para ver los totales recalculados.")

    def accion_fecha_corte_automatica(self):
        ops.volver_fecha_corte_automatica(self.usuario)
        self.fecha_corte_oficial = ops.obtener_fecha_corte_oficial()
        self._actualizar_encabezado_fecha_corte()
        messagebox.showinfo("Listo", f"La fecha de corte vuelve a ser automática: "
                             f"{fecha_es(self.fecha_corte_oficial.isoformat())} "
                             f"(31/12 del año actual, se va a actualizar sola cada año).")

    def accion_cambiar_usuario(self):
        self.usuario = None
        self._pedir_usuario_nuevo()
        self.set_status(f"Usuario actual: {self.usuario}")

    def accion_recalcular_reglas(self):
        if not messagebox.askyesno(
                "Confirmar",
                "Esto va a revisar TODOS los agentes y volver a aplicar:\n\n"
                "1) Para Nivel A/B: contar el ascenso desde la fecha de "
                "titulación (sólo si no hay una fecha ya puesta a mano).\n"
                "2) Ascenso de grado 1421 por tipo de período anterior: "
                "Niveles C/D/E cuentan todo excepto 'Priv'; Niveles A/B "
                "cuentan todo excepto 'Priv' y 'Pas'.\n"
                "3) Antigüedad en la Administración Pública Nacional: "
                "cuenta todo excepto 'Priv' (para todos los niveles).\n\n"
                "Es útil después de cargar agentes o períodos nuevos. "
                "No pisa fechas que ya hayas configurado a mano.\n\n"
                "¿Continuar?"):
            return
        aplicados_titulacion = ops.aplicar_default_titulacion_ab_todos(self.usuario)
        resumen_tipo = ops.aplicar_regla_tipo_periodo_por_nivel(self.usuario)
        resumen_apn = ops.aplicar_regla_apn_por_tipo(self.usuario)
        if self.n_doc_actual:
            self._cargar_ficha(self.n_doc_actual)
        messagebox.showinfo(
            "Listo",
            f"Fecha de titulación aplicada a {len(aplicados_titulacion)} agente(s) nuevos.\n\n"
            f"Ascenso de grado 1421 -- períodos revisados: {resumen_tipo['revisados']}, "
            f"modificados: {resumen_tipo['modificados']}\n"
            f"Agentes sin nivel cargado (omitidos, revisar a mano): {resumen_tipo['sin_nivel_omitidos']}\n\n"
            f"Antigüedad APN -- períodos revisados: {resumen_apn['revisados']}, "
            f"modificados: {resumen_apn['modificados']}")

    def _actualizar_encabezado_fecha_corte(self):
        self.lbl_fecha_corte_header.config(text=f"Fecha de corte: {fecha_es(self.fecha_corte_oficial.isoformat())}  ")

    def _refrescar_resumen(self):
        r = ops.resumen_clasificacion_1421()
        self.set_status(f"Listo. {r['cuentan_1421']} agentes del Decreto 1421/02 cargados en el sistema.")


def main():
    init_db()
    ok, detalle = verificar_integridad()
    app = App()
    if not ok:
        messagebox.showwarning("Atención", f"La base reporta un problema de integridad:\n{detalle}\n"
                                "Se recomienda restaurar desde el último backup.")
    app.mainloop()


if __name__ == "__main__":
    main()
