"""
operaciones.py - Operaciones de negocio expuestas al CLI (y reusables desde
cualquier otra interfaz que se quiera construir después: web, Excel, etc.)

Cada función de escritura usa db.Transaccion, por lo que:
  * hace backup del .db antes de tocar nada
  * corre en una transacción real (todo o nada)
  * deja rastro en `auditoria`
"""

from datetime import date, datetime, timedelta
from typing import Optional, List

from db import Transaccion, registrar_auditoria, get_connection, row_to_dict
from antiguedad import Periodo, evaluar_agente_anio, antiguedad_computable_dias, texto_antiguedad


def _parse_fecha(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


# ------------------------------------------------------------------
# CONSULTAS (sólo lectura)
# ------------------------------------------------------------------

def obtener_fecha_corte_oficial() -> date:
    """Fecha de corte para calcular antigüedad en las fichas.
    Por defecto es automática: el 31 de diciembre del año actual (se
    actualiza sola cada año). Si se configuró una fecha manual (menú
    Sistema -> Cambiar fecha de corte), se usa esa en su lugar."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT valor FROM metadata WHERE clave='fecha_corte_manual'").fetchone()
        if row and row["valor"]:
            return _parse_fecha(row["valor"])
        return date(date.today().year, 12, 31)
    finally:
        conn.close()


def fecha_corte_es_manual() -> bool:
    conn = get_connection()
    try:
        row = conn.execute("SELECT valor FROM metadata WHERE clave='fecha_corte_manual'").fetchone()
        return bool(row and row["valor"])
    finally:
        conn.close()


def set_fecha_corte_oficial(fecha: str, usuario: str):
    with Transaccion("set_fecha_corte_oficial") as conn:
        anterior = conn.execute("SELECT valor FROM metadata WHERE clave='fecha_corte_manual'").fetchone()
        conn.execute("INSERT OR REPLACE INTO metadata (clave, valor) VALUES ('fecha_corte_manual', ?)", (fecha,))
        registrar_auditoria(conn, "metadata", "UPDATE" if anterior else "INSERT", "fecha_corte_manual",
                             row_to_dict(anterior), {"valor": fecha}, usuario)


def volver_fecha_corte_automatica(usuario: str):
    with Transaccion("volver_fecha_corte_automatica") as conn:
        anterior = conn.execute("SELECT valor FROM metadata WHERE clave='fecha_corte_manual'").fetchone()
        conn.execute("DELETE FROM metadata WHERE clave='fecha_corte_manual'")
        if anterior:
            registrar_auditoria(conn, "metadata", "SOFT_DELETE", "fecha_corte_manual",
                                 row_to_dict(anterior), None, usuario)


def buscar_agentes(texto: str, incluir_inactivos=False, limite=30, solo_1421=True):
    conn = get_connection()
    try:
        texto = f"%{texto.strip()}%"
        query = "SELECT * FROM agentes WHERE (apellido_nombre LIKE ? OR CAST(n_doc AS TEXT) LIKE ?)"
        params = [texto, texto]
        if not incluir_inactivos:
            query += " AND activo=1"
        if solo_1421:
            query += " AND cuenta_1421=1"
        query += " ORDER BY apellido_nombre LIMIT ?"
        params.append(limite)
        rows = conn.execute(query, params).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


def obtener_agente(n_doc: int):
    conn = get_connection()
    try:
        agente = conn.execute("SELECT * FROM agentes WHERE n_doc=?", (n_doc,)).fetchone()
        if not agente:
            return None
        agente = row_to_dict(agente)
        agente["periodos"] = [row_to_dict(r) for r in conn.execute(
            "SELECT * FROM periodos_antiguedad WHERE n_doc=? AND activo=1 ORDER BY fecha_desde", (n_doc,))]
        agente["config"] = row_to_dict(conn.execute(
            "SELECT * FROM config_agente WHERE n_doc=?", (n_doc,)).fetchone())
        agente["titulos"] = [row_to_dict(r) for r in conn.execute(
            "SELECT * FROM titulos WHERE n_doc=? AND activo=1 ORDER BY fecha_titulacion", (n_doc,))]
        agente["titulos_grado"] = [t for t in agente["titulos"] if t["es_titulo_grado"]]
        return agente
    finally:
        conn.close()


def calcular_antiguedad_agente(n_doc: int, fecha_corte: Optional[date] = None):
    """Calcula ambos totales a una fecha dada (por defecto: hoy), SIN persistir nada:
      - antigüedad_1421: sólo períodos marcados cuenta_ascenso=1 (para el ascenso de grado)
      - antigüedad_apn: períodos marcados suma_apn=1 (Administración Pública Nacional, incluye
        servicios anteriores como pasantías aunque no cuenten para el ascenso de grado)
    """
    agente = obtener_agente(n_doc)
    if agente is None:
        return None
    fecha_corte = fecha_corte or obtener_fecha_corte_oficial()
    cfg = agente["config"] or {}
    inicio = _parse_fecha(cfg.get("fecha_inicio_conteo_grado"))
    cierre = _parse_fecha(cfg.get("fecha_cierre_conteo"))
    grado_base = cfg.get("grado_base", 0) or 0

    periodos = [
        Periodo(
            fecha_desde=_parse_fecha(p["fecha_desde"]),
            fecha_hasta=_parse_fecha(p["fecha_hasta"]),
            cuenta_ascenso=bool(p["cuenta_ascenso"]),
            organismo=p["organismo"] or "",
            suma_apn=bool(p.get("suma_apn", 1)),
            tipo_prestacion=p.get("tipo_prestacion") or "",
        )
        for p in agente["periodos"]
    ]
    dias_1421 = antiguedad_computable_dias(periodos, fecha_corte, inicio, cierre, criterio="cuenta_ascenso")
    dias_apn = antiguedad_computable_dias(periodos, fecha_corte, criterio="suma_apn")
    return {
        "n_doc": n_doc,
        "apellido_nombre": agente["apellido_nombre"],
        "fecha_corte": fecha_corte.isoformat(),
        "antiguedad_dias": dias_1421,
        "antiguedad_texto": texto_antiguedad(dias_1421),
        "antiguedad_apn_dias": dias_apn,
        "antiguedad_apn_texto": texto_antiguedad(dias_apn),
        "grado_base": grado_base,
    }


def evaluar_ascenso_agente(n_doc: int, anio: int, persistir=False, usuario=None, fecha_corte: Optional[date] = None):
    agente = obtener_agente(n_doc)
    if agente is None:
        return None
    cfg = agente["config"] or {}
    inicio = _parse_fecha(cfg.get("fecha_inicio_conteo_grado"))
    cierre = _parse_fecha(cfg.get("fecha_cierre_conteo"))
    grado_base = cfg.get("grado_base", 0) or 0

    periodos = [
        Periodo(
            fecha_desde=_parse_fecha(p["fecha_desde"]),
            fecha_hasta=_parse_fecha(p["fecha_hasta"]),
            cuenta_ascenso=bool(p["cuenta_ascenso"]),
            organismo=p["organismo"] or "",
        )
        for p in agente["periodos"]
    ]
    resultado = evaluar_agente_anio(periodos, anio, inicio, cierre, grado_base, fecha_corte=fecha_corte)
    resultado["n_doc"] = n_doc
    resultado["apellido_nombre"] = agente["apellido_nombre"]

    if persistir:
        with Transaccion(f"calculo_ascenso_{n_doc}_{anio}") as conn:
            cur = conn.execute(
                """INSERT INTO calculos_ascenso
                       (n_doc, anio_evaluado, antiguedad_computable_dias, antiguedad_computable_texto,
                        grados_acumulados, grados_anio_anterior, asciende, grados_nuevos,
                        fecha_efectiva_ascenso, usuario_corrida)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (n_doc, anio, resultado["antiguedad_computable_dias"], resultado["antiguedad_computable_texto"],
                 resultado["grados_acumulados"], resultado["grados_anio_anterior"], int(resultado["asciende"]),
                 resultado["grados_nuevos"], resultado["fecha_efectiva_ascenso"], usuario),
            )
            registrar_auditoria(conn, "calculos_ascenso", "INSERT", cur.lastrowid, None, resultado, usuario)
    return resultado


def listar_ascensos_anio(anio: int, solo_activos=True, solo_1421=True, fecha_corte: Optional[date] = None):
    """Evalúa a TODOS los agentes para el año dado y devuelve quiénes ascienden.
    Por defecto sólo considera agentes con cuenta_1421=1 (contratados bajo
    Decreto 1421/02, sin fecha de baja registrada). `fecha_corte` permite
    evaluar en una fecha específica en vez del 31/12 por defecto."""
    conn = get_connection()
    try:
        query = "SELECT n_doc FROM agentes WHERE 1=1"
        if solo_activos:
            query += " AND activo=1"
        if solo_1421:
            query += " AND cuenta_1421=1"
        docs = [r["n_doc"] for r in conn.execute(query)]
    finally:
        conn.close()

    resultados = []
    for n_doc in docs:
        r = evaluar_ascenso_agente(n_doc, anio, persistir=False, fecha_corte=fecha_corte)
        if r and r["asciende"]:
            resultados.append(r)
    resultados.sort(key=lambda x: x["apellido_nombre"])
    return resultados


def clasificacion_1421(n_doc: int):
    """Devuelve el detalle de por qué un agente cuenta o no bajo el filtro 1421."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT n_doc, apellido_nombre, vinculado_1421, tiene_baja_1421, cuenta_1421, motivo_clasif_1421 "
            "FROM agentes WHERE n_doc=?", (n_doc,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def resumen_clasificacion_1421():
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) c FROM agentes").fetchone()["c"]
        cuentan = conn.execute("SELECT COUNT(*) c FROM agentes WHERE cuenta_1421=1").fetchone()["c"]
        vinculados = conn.execute("SELECT COUNT(*) c FROM agentes WHERE vinculado_1421=1").fetchone()["c"]
        excluidos_baja = conn.execute(
            "SELECT COUNT(*) c FROM agentes WHERE vinculado_1421=1 AND tiene_baja_1421=1").fetchone()["c"]
        no_vinculados = conn.execute("SELECT COUNT(*) c FROM agentes WHERE vinculado_1421=0").fetchone()["c"]
        return {"total_agentes": total, "cuentan_1421": cuentan, "vinculados_1421": vinculados,
                "excluidos_por_baja": excluidos_baja, "no_vinculados": no_vinculados}
    finally:
        conn.close()


def editar_datos_agente(n_doc: int, usuario: str, nivel_actual=None, grado_actual=None,
                         dependencia_1421=None):
    """Edita los datos informativos del agente (nivel, grado mostrado, dependencia).
    Sólo actualiza los campos que se pasen (no None)."""
    campos = {}
    if nivel_actual is not None:
        campos["nivel_actual"] = nivel_actual or None
    if grado_actual is not None:
        campos["grado_actual"] = grado_actual
    if dependencia_1421 is not None:
        campos["dependencia_1421"] = dependencia_1421 or None
    if not campos:
        return
    with Transaccion(f"editar_agente_{n_doc}") as conn:
        anterior = conn.execute("SELECT * FROM agentes WHERE n_doc=?", (n_doc,)).fetchone()
        if not anterior:
            raise ValueError(f"No existe el agente {n_doc}")
        anterior = row_to_dict(anterior)
        sets = ", ".join(f"{k}=?" for k in campos)
        valores = list(campos.values()) + [datetime.now().isoformat(), usuario, n_doc]
        conn.execute(f"UPDATE agentes SET {sets}, fecha_modif=?, usuario_modif=? WHERE n_doc=?", valores)
        nuevo = {**anterior, **campos}
        registrar_auditoria(conn, "agentes", "UPDATE", n_doc, anterior, nuevo, usuario)


def editar_titulo_grado(n_doc: int, usuario: str, titulo=None, institucion=None,
                         fecha_titulacion=None, fecha_egreso=None):
    """Crea o actualiza el título de grado (universitario) del agente."""
    with Transaccion(f"editar_titulo_{n_doc}") as conn:
        existente = conn.execute(
            "SELECT * FROM titulos WHERE n_doc=? AND es_titulo_grado=1 AND activo=1 LIMIT 1", (n_doc,)).fetchone()
        if existente:
            anterior = row_to_dict(existente)
            campos = {}
            if titulo is not None:
                campos["titulo"] = titulo or None
            if institucion is not None:
                campos["institucion"] = institucion or None
            if fecha_titulacion is not None:
                campos["fecha_titulacion"] = fecha_titulacion or None
            if fecha_egreso is not None:
                campos["fecha_egreso"] = fecha_egreso or None
            if campos:
                sets = ", ".join(f"{k}=?" for k in campos)
                conn.execute(f"UPDATE titulos SET {sets} WHERE id=?", list(campos.values()) + [existente["id"]])
                nuevo = {**anterior, **campos}
                registrar_auditoria(conn, "titulos", "UPDATE", existente["id"], anterior, nuevo, usuario)
        else:
            agente = conn.execute("SELECT n_doc FROM agentes WHERE n_doc=?", (n_doc,)).fetchone()
            if not agente:
                raise ValueError(f"No existe el agente {n_doc}")
            cur = conn.execute(
                """INSERT INTO titulos (n_doc, id_niv, titulo, institucion, fecha_titulacion,
                                         fecha_egreso, es_titulo_grado, origen)
                   VALUES (?, 'U', ?, ?, ?, ?, 1, 'manual')""",
                (n_doc, titulo or None, institucion or None, fecha_titulacion or None, fecha_egreso or None),
            )
            registrar_auditoria(conn, "titulos", "INSERT", cur.lastrowid, None,
                                 {"n_doc": n_doc, "titulo": titulo, "es_titulo_grado": 1}, usuario)


def aplicar_default_titulacion_ab(n_doc: int, usuario: str) -> bool:
    """Regla por defecto: para agentes Nivel A o B, si todavía no se
    configuró una fecha de inicio de cómputo de grado y el agente tiene
    un título de grado con fecha de titulación, se usa esa fecha como
    punto de partida automáticamente. No pisa una fecha ya configurada
    a mano. Devuelve True si aplicó el default."""
    agente = obtener_agente(n_doc)
    if not agente:
        return False
    nivel = (agente.get("nivel_actual") or "").strip().upper()
    if nivel not in ("A", "B"):
        return False
    cfg = agente.get("config") or {}
    if cfg.get("fecha_inicio_conteo_grado"):
        return False  # ya hay una fecha (a mano o de una corrida anterior de esta regla) -> no se toca
    if not agente["titulos_grado"]:
        return False
    fecha_tit = agente["titulos_grado"][0].get("fecha_titulacion")
    if not fecha_tit:
        return False
    set_config_agente(n_doc, usuario, fecha_inicio_conteo_grado=fecha_tit)
    return True


def aplicar_default_titulacion_ab_todos(usuario: str):
    """Corre la regla de arriba para todos los agentes que cuentan en el
    sistema. Devuelve la lista de n_doc a los que se les aplicó."""
    conn = get_connection()
    try:
        docs = [r["n_doc"] for r in conn.execute("SELECT n_doc FROM agentes WHERE cuenta_1421=1")]
    finally:
        conn.close()
    aplicados = []
    for n_doc in docs:
        if aplicar_default_titulacion_ab(n_doc, usuario):
            aplicados.append(n_doc)
    return aplicados


def aplicar_regla_tipo_periodo_por_nivel(usuario: str):
    """
    Regla de negocio (confirmada por el usuario, agosto 2026):
      - Niveles C, D, E: cuenta TODA la antigüedad para el ascenso de
        grado 1421, EXCEPTO los períodos tipo 'Priv' (sector privado).
      - Niveles A, B: cuenta TODA la antigüedad EXCEPTO 'Priv' y 'Pas'
        (pasantía), pero sólo a partir de la fecha de titulación (eso
        ya lo maneja aplicar_default_titulacion_ab / la fecha de inicio
        de conteo configurada).
      - Sólo se tocan los períodos importados de servicios anteriores
        (origen='importado_nac_priv'); el período del Ministerio y los
        cargados a mano no se modifican acá.
      - Si el nivel del agente no está cargado (None/vacío), no se
        toca nada para ese agente -- queda para revisión manual.

    Devuelve un resumen con la cantidad de períodos que cambiaron.
    """
    conn = get_connection()
    try:
        filas = conn.execute("""
            SELECT p.id, p.n_doc, p.tipo_prestacion, p.cuenta_ascenso, a.nivel_actual
            FROM periodos_antiguedad p
            JOIN agentes a ON a.n_doc = p.n_doc
            WHERE p.origen='importado_nac_priv' AND p.activo=1
        """).fetchall()
    finally:
        conn.close()

    resumen = {"revisados": 0, "modificados": 0, "sin_nivel_omitidos": 0, "por_tipo": {}}
    with Transaccion("aplicar_regla_tipo_periodo_por_nivel") as conn:
        for f in filas:
            resumen["revisados"] += 1
            nivel = (f["nivel_actual"] or "").strip().upper()
            tipo = (f["tipo_prestacion"] or "").strip()

            if not nivel:
                resumen["sin_nivel_omitidos"] += 1
                continue

            if nivel in ("A", "B"):
                nuevo_cuenta = 0 if tipo in ("Priv", "Pas") else 1
            else:  # C, D, E (y cualquier otro nivel no A/B se trata igual: todo cuenta excepto Priv)
                nuevo_cuenta = 0 if tipo == "Priv" else 1

            if nuevo_cuenta != f["cuenta_ascenso"]:
                anterior = {"cuenta_ascenso": f["cuenta_ascenso"]}
                conn.execute(
                    "UPDATE periodos_antiguedad SET cuenta_ascenso=?, fecha_modif=?, usuario_modif=? WHERE id=?",
                    (nuevo_cuenta, datetime.now().isoformat(), usuario, f["id"]),
                )
                registrar_auditoria(conn, "periodos_antiguedad", "UPDATE", f["id"], anterior,
                                     {"cuenta_ascenso": nuevo_cuenta,
                                      "motivo": f"regla por nivel {nivel} / tipo {tipo}"}, usuario)
                resumen["modificados"] += 1
                resumen["por_tipo"][tipo] = resumen["por_tipo"].get(tipo, 0) + 1

        conn.execute(
            "INSERT OR REPLACE INTO metadata (clave, valor) VALUES ('regla_tipo_periodo_por_nivel_fecha', ?)",
            (datetime.now().isoformat(),),
        )

    return resumen


# ------------------------------------------------------------------
# ESCRITURA (todas con transacción + backup + auditoría)
# ------------------------------------------------------------------

def cargar_periodo(n_doc: int, fecha_desde: str, fecha_hasta: Optional[str],
                    organismo: str, cuenta_ascenso: bool, observaciones: str, usuario: str,
                    tipo_prestacion: Optional[str] = None, suma_apn: bool = True):
    with Transaccion(f"cargar_periodo_{n_doc}") as conn:
        agente = conn.execute("SELECT n_doc FROM agentes WHERE n_doc=?", (n_doc,)).fetchone()
        if not agente:
            raise ValueError(f"No existe el agente {n_doc}. Debe crearse primero.")
        cur = conn.execute(
            """INSERT INTO periodos_antiguedad
                   (n_doc, fecha_desde, fecha_hasta, organismo, cuenta_ascenso,
                    observaciones, origen, usuario_carga, tipo_prestacion, suma_apn)
               VALUES (?, ?, ?, ?, ?, ?, 'manual', ?, ?, ?)""",
            (n_doc, fecha_desde, fecha_hasta, organismo, int(cuenta_ascenso), observaciones, usuario,
             tipo_prestacion or None, int(suma_apn)),
        )
        nuevo = {
            "n_doc": n_doc, "fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta,
            "organismo": organismo, "cuenta_ascenso": int(cuenta_ascenso), "observaciones": observaciones,
            "tipo_prestacion": tipo_prestacion, "suma_apn": int(suma_apn),
        }
        registrar_auditoria(conn, "periodos_antiguedad", "INSERT", cur.lastrowid, None, nuevo, usuario)
        return cur.lastrowid


def modificar_periodo(periodo_id: int, usuario: str, **cambios):
    """cambios puede incluir: fecha_desde, fecha_hasta, organismo, cuenta_ascenso, observaciones,
    tipo_prestacion, suma_apn"""
    campos_validos = {"fecha_desde", "fecha_hasta", "organismo", "cuenta_ascenso", "observaciones",
                       "tipo_prestacion", "suma_apn"}
    cambios = {k: v for k, v in cambios.items() if k in campos_validos}
    if not cambios:
        return

    with Transaccion(f"modificar_periodo_{periodo_id}") as conn:
        anterior = conn.execute("SELECT * FROM periodos_antiguedad WHERE id=?", (periodo_id,)).fetchone()
        if not anterior:
            raise ValueError(f"No existe el período {periodo_id}")
        anterior = row_to_dict(anterior)

        sets = ", ".join(f"{k}=?" for k in cambios)
        valores = list(cambios.values())
        valores += [datetime.now().isoformat(), usuario, periodo_id]
        conn.execute(
            f"UPDATE periodos_antiguedad SET {sets}, fecha_modif=?, usuario_modif=? WHERE id=?",
            valores,
        )
        nuevo = {**anterior, **cambios}
        registrar_auditoria(conn, "periodos_antiguedad", "UPDATE", periodo_id, anterior, nuevo, usuario)


def marcar_cuenta_ascenso(periodo_id: int, cuenta: bool, usuario: str):
    modificar_periodo(periodo_id, usuario, cuenta_ascenso=int(cuenta))


def desactivar_periodo(periodo_id: int, usuario: str, motivo: str = ""):
    """Soft-delete: nunca se borra físicamente."""
    with Transaccion(f"desactivar_periodo_{periodo_id}") as conn:
        anterior = conn.execute("SELECT * FROM periodos_antiguedad WHERE id=?", (periodo_id,)).fetchone()
        if not anterior:
            raise ValueError(f"No existe el período {periodo_id}")
        anterior = row_to_dict(anterior)
        conn.execute(
            "UPDATE periodos_antiguedad SET activo=0, observaciones=?, fecha_modif=?, usuario_modif=? WHERE id=?",
            (f"{anterior.get('observaciones') or ''} [DESACTIVADO: {motivo}]".strip(),
             datetime.now().isoformat(), usuario, periodo_id),
        )
        registrar_auditoria(conn, "periodos_antiguedad", "SOFT_DELETE", periodo_id, anterior,
                             {"activo": 0, "motivo": motivo}, usuario)


def cortar_periodo_por_licencia(periodo_id: int, licencia_desde: str, licencia_hasta: str,
                                 usuario: str, motivo: str = ""):
    """Divide un período existente en dos, excluyendo un tramo intermedio
    (licencia extraordinaria sin goce, excedencia, etc.) que no debe contar
    para el cómputo de antigüedad.

    No cambia ningún cálculo: el motor de antigüedad (antiguedad.py) ya
    suma correctamente varios períodos separados por unión de intervalos.
    Esto sólo automatiza la carga: acorta el período existente hasta el
    día anterior a la licencia, y (si corresponde) crea uno nuevo desde el
    día siguiente a la licencia hasta donde llegaba el original, con los
    mismos datos (organismo, cuenta_ascenso, tipo, APN).

    Devuelve (periodo_id_original, periodo_id_nuevo_o_None). Es None si la
    licencia llega justo hasta el final del período (no hace falta un
    tramo posterior, sólo se acorta el original).
    """
    d_licencia = _parse_fecha(licencia_desde)
    h_licencia = _parse_fecha(licencia_hasta)
    if not d_licencia or not h_licencia:
        raise ValueError("Las fechas de la licencia son obligatorias (AAAA-MM-DD).")
    if h_licencia < d_licencia:
        raise ValueError("La fecha 'hasta' de la licencia no puede ser anterior a la fecha 'desde'.")

    with Transaccion(f"cortar_periodo_licencia_{periodo_id}") as conn:
        original = conn.execute("SELECT * FROM periodos_antiguedad WHERE id=?", (periodo_id,)).fetchone()
        if not original:
            raise ValueError(f"No existe el período {periodo_id}")
        original = row_to_dict(original)

        fecha_desde_orig = _parse_fecha(original["fecha_desde"])
        fecha_hasta_orig = _parse_fecha(original["fecha_hasta"])  # None si vigente

        if d_licencia <= fecha_desde_orig:
            raise ValueError(
                "La licencia no puede empezar en la fecha de inicio del período (o antes). "
                "Si la licencia arranca desde el principio, corregí directamente la fecha "
                "'desde' del período con 'Modificar seleccionado' en vez de cortarlo."
            )
        if fecha_hasta_orig and h_licencia > fecha_hasta_orig:
            raise ValueError("La licencia termina después de la fecha 'hasta' del período.")

        nueva_hasta_original = (d_licencia - timedelta(days=1)).isoformat()
        nueva_desde_siguiente = h_licencia + timedelta(days=1)
        detalle_motivo = f"licencia {licencia_desde} a {licencia_hasta}" + (f": {motivo}" if motivo else "")

        conn.execute(
            "UPDATE periodos_antiguedad SET fecha_hasta=?, fecha_modif=?, usuario_modif=? WHERE id=?",
            (nueva_hasta_original, datetime.now().isoformat(), usuario, periodo_id),
        )
        registrar_auditoria(conn, "periodos_antiguedad", "UPDATE", periodo_id,
                             {"fecha_hasta": original["fecha_hasta"]},
                             {"fecha_hasta": nueva_hasta_original, "motivo": f"cortado por {detalle_motivo}"},
                             usuario)

        nuevo_id = None
        # Si la licencia no llega hasta el final del período (o el período era
        # vigente, sin fecha_hasta), se crea el tramo posterior a la licencia.
        if fecha_hasta_orig is None or nueva_desde_siguiente <= fecha_hasta_orig:
            cur = conn.execute(
                """INSERT INTO periodos_antiguedad
                       (n_doc, fecha_desde, fecha_hasta, organismo, cuenta_ascenso, observaciones,
                        origen, usuario_carga, tipo_prestacion, suma_apn)
                   VALUES (?, ?, ?, ?, ?, ?, 'manual', ?, ?, ?)""",
                (original["n_doc"], nueva_desde_siguiente.isoformat(), original["fecha_hasta"],
                 original["organismo"], original["cuenta_ascenso"],
                 f"Continuación del período #{periodo_id} tras {detalle_motivo}.",
                 usuario, original["tipo_prestacion"], original["suma_apn"]),
            )
            nuevo_id = cur.lastrowid
            registrar_auditoria(conn, "periodos_antiguedad", "INSERT", nuevo_id, None,
                                 {"n_doc": original["n_doc"], "fecha_desde": nueva_desde_siguiente.isoformat(),
                                  "continuacion_de": periodo_id}, usuario)

        return periodo_id, nuevo_id


def set_config_agente(n_doc: int, usuario: str, fecha_inicio_conteo_grado: Optional[str] = None,
                       fecha_cierre_conteo: Optional[str] = None, grado_base: Optional[int] = None,
                       observaciones: Optional[str] = None):
    with Transaccion(f"config_agente_{n_doc}") as conn:
        agente = conn.execute("SELECT n_doc FROM agentes WHERE n_doc=?", (n_doc,)).fetchone()
        if not agente:
            raise ValueError(f"No existe el agente {n_doc}")
        anterior = conn.execute("SELECT * FROM config_agente WHERE n_doc=?", (n_doc,)).fetchone()
        anterior = row_to_dict(anterior)

        actual = dict(anterior) if anterior else {"n_doc": n_doc}
        if fecha_inicio_conteo_grado is not None:
            actual["fecha_inicio_conteo_grado"] = fecha_inicio_conteo_grado
        if fecha_cierre_conteo is not None:
            actual["fecha_cierre_conteo"] = fecha_cierre_conteo
        if grado_base is not None:
            actual["grado_base"] = grado_base
        if observaciones is not None:
            actual["observaciones"] = observaciones

        conn.execute(
            """INSERT INTO config_agente (n_doc, fecha_inicio_conteo_grado, fecha_cierre_conteo,
                                           grado_base, observaciones, usuario_modif)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(n_doc) DO UPDATE SET
                    fecha_inicio_conteo_grado=excluded.fecha_inicio_conteo_grado,
                    fecha_cierre_conteo=excluded.fecha_cierre_conteo,
                    grado_base=excluded.grado_base,
                    observaciones=excluded.observaciones,
                    fecha_modif=datetime('now'),
                    usuario_modif=excluded.usuario_modif""",
            (n_doc, actual.get("fecha_inicio_conteo_grado"), actual.get("fecha_cierre_conteo"),
             actual.get("grado_base", 0), actual.get("observaciones"), usuario),
        )
        registrar_auditoria(conn, "config_agente", "UPDATE" if anterior else "INSERT",
                             n_doc, anterior, actual, usuario)


def crear_agente_manual(n_doc: int, apellido_nombre: str, usuario: str,
                         nivel_actual: Optional[str] = None, grado_actual: Optional[int] = None):
    with Transaccion(f"crear_agente_{n_doc}") as conn:
        existe = conn.execute("SELECT n_doc FROM agentes WHERE n_doc=?", (n_doc,)).fetchone()
        if existe:
            raise ValueError(f"Ya existe un agente con documento {n_doc}")
        conn.execute(
            """INSERT INTO agentes (n_doc, apellido_nombre, nivel_actual, grado_actual, origen, usuario_modif)
               VALUES (?, ?, ?, ?, 'manual', ?)""",
            (n_doc, apellido_nombre, nivel_actual, grado_actual, usuario),
        )
        conn.execute("INSERT INTO config_agente (n_doc, usuario_modif) VALUES (?, ?)", (n_doc, usuario))
        registrar_auditoria(conn, "agentes", "INSERT", n_doc, None,
                             {"n_doc": n_doc, "apellido_nombre": apellido_nombre}, usuario)


def aplicar_regla_apn_por_tipo(usuario: str):
    """
    Regla de negocio (confirmada por el usuario, agosto 2026):
    TODA la antigüedad cuenta para "Administración Pública Nacional",
    EXCEPTO los períodos de tipo 'Priv' (actividad privada). No depende
    del nivel del agente (a diferencia de la regla de ascenso de grado).

    Corrige el campo suma_apn de los períodos importados de servicios
    anteriores (origen='importado_nac_priv'); el período del Ministerio
    y los cargados a mano no se tocan acá.
    """
    conn = get_connection()
    try:
        filas = conn.execute("""
            SELECT id, n_doc, tipo_prestacion, suma_apn FROM periodos_antiguedad
            WHERE origen='importado_nac_priv' AND activo=1
        """).fetchall()
    finally:
        conn.close()

    resumen = {"revisados": 0, "modificados": 0, "por_tipo": {}}
    with Transaccion("aplicar_regla_apn_por_tipo") as conn:
        for f in filas:
            resumen["revisados"] += 1
            tipo = (f["tipo_prestacion"] or "").strip()
            nuevo_suma = 0 if tipo == "Priv" else 1

            if nuevo_suma != f["suma_apn"]:
                anterior = {"suma_apn": f["suma_apn"]}
                conn.execute(
                    "UPDATE periodos_antiguedad SET suma_apn=?, fecha_modif=?, usuario_modif=? WHERE id=?",
                    (nuevo_suma, datetime.now().isoformat(), usuario, f["id"]),
                )
                registrar_auditoria(conn, "periodos_antiguedad", "UPDATE", f["id"], anterior,
                                     {"suma_apn": nuevo_suma, "motivo": f"regla APN por tipo {tipo}"}, usuario)
                resumen["modificados"] += 1
                resumen["por_tipo"][tipo] = resumen["por_tipo"].get(tipo, 0) + 1

        conn.execute(
            "INSERT OR REPLACE INTO metadata (clave, valor) VALUES ('regla_apn_por_tipo_fecha', ?)",
            (datetime.now().isoformat(),),
        )

    return resumen


def listar_agentes_activos(solo_1421=True):
    """Devuelve la lista completa de agentes activos con su antigüedad
    calculada, para pantalla o exportación."""
    conn = get_connection()
    try:
        query = "SELECT n_doc FROM agentes WHERE activo=1"
        if solo_1421:
            query += " AND cuenta_1421=1"
        query += " ORDER BY apellido_nombre"
        docs = [r["n_doc"] for r in conn.execute(query)]
    finally:
        conn.close()

    fecha_corte = obtener_fecha_corte_oficial()
    resultados = []
    for n_doc in docs:
        a = obtener_agente(n_doc)
        calc = calcular_antiguedad_agente(n_doc, fecha_corte)
        titulo = a["titulos_grado"][0] if a["titulos_grado"] else {}
        resultados.append({
            "n_doc": n_doc,
            "apellido_nombre": a["apellido_nombre"],
            "nivel_actual": a["nivel_actual"],
            "grado_actual": a["grado_actual"],
            "dependencia_1421": a.get("dependencia_1421"),
            "titulo": titulo.get("titulo"),
            "fecha_titulacion": titulo.get("fecha_titulacion"),
            "antiguedad_1421_texto": calc["antiguedad_texto"],
            "antiguedad_apn_texto": calc["antiguedad_apn_texto"],
        })
    return sorted(resultados, key=lambda r: r["apellido_nombre"])


def contar_agentes_activos(solo_1421=True) -> int:
    conn = get_connection()
    try:
        query = "SELECT COUNT(*) c FROM agentes WHERE activo=1"
        if solo_1421:
            query += " AND cuenta_1421=1"
        return conn.execute(query).fetchone()["c"]
    finally:
        conn.close()
