"""Corrección puntual: ALFONZO, Yésica Lorena estaba cargada con el DNI
29946105 (el que usan CONTRATADOS/Listado_1421), pero su DNI real es
29946405 (el que usan DPersonales/Nac_Priv/Agente_titulo, confirmado
por el reporte real de Access que mostró el usuario). Se crea el
registro correcto con todos sus datos, y se marca el registro viejo
como duplicado erróneo (sin borrarlo)."""
from datetime import datetime
from db import init_db, Transaccion, registrar_auditoria, get_connection

DOC_VIEJO = 29946105
DOC_CORRECTO = 29946405

init_db()

with Transaccion("correccion_dni_alfonzo") as conn:
    viejo = conn.execute("SELECT * FROM agentes WHERE n_doc=?", (DOC_VIEJO,)).fetchone()
    assert viejo, "no se encontró el registro viejo"
    viejo = dict(viejo)

    # 1) crear el agente con el DNI correcto, con los mismos datos de nivel/grado/dependencia
    conn.execute(
        """INSERT INTO agentes (n_doc, apellido_nombre, nivel_actual, grado_actual, activo, origen,
                                 usuario_modif, vinculado_1421, tiene_baja_1421, cuenta_1421,
                                 motivo_clasif_1421, dependencia_1421, contrato_desde_1421, contrato_hasta_1421)
           VALUES (?, ?, ?, ?, 1, 'importado_faltante', ?, 1, 0, 1,
                   'Vinculado a Decreto 1421/02. DNI corregido: CONTRATADOS/Listado_1421 tenian 29946105, el correcto (confirmado con reporte de Access real) es 29946405, coincide con DPersonales/Nac_Priv/Agente_titulo.',
                   ?, ?, ?)""",
        (DOC_CORRECTO, viejo["apellido_nombre"], viejo["nivel_actual"], viejo["grado_actual"], "Ariel",
         viejo["dependencia_1421"], viejo["contrato_desde_1421"], viejo["contrato_hasta_1421"]),
    )
    registrar_auditoria(conn, "agentes", "INSERT", DOC_CORRECTO, None,
                         {"motivo": "corrección de DNI de ALFONZO, ver auditoría de 29946105"}, "Ariel")
    conn.execute("INSERT INTO config_agente (n_doc, usuario_modif) VALUES (?, ?)", (DOC_CORRECTO, "Ariel"))

    # 2) sus 2 períodos previos (SEC. GRAL de PRES. NAC., tipo Nac) desde Nac_Priv
    periodos = [
        ("2006-03-01", "2011-12-20", "SEC. GRAL de PRES. NAC.", "Nac", "Cont. 1421/02", "MOBI - Continua Ctro. 1421/02", 1),
        ("2011-12-21", "2026-03-30", "SEC. GRAL de PRES. NAC.", "Nac", "Cont. 1421/02", "", 0),
    ]
    for desde, hasta, organismo, tipo, planta, motivo_baja, suma_apn in periodos:
        # regla ya confirmada: Nivel B cuenta todo excepto Priv/Pas -> 'Nac' cuenta
        cur = conn.execute(
            """INSERT INTO periodos_antiguedad
                   (n_doc, fecha_desde, fecha_hasta, organismo, cuenta_ascenso, observaciones,
                    origen, usuario_carga, tipo_prestacion, suma_apn, planta_nac, motivo_baja)
               VALUES (?, ?, ?, ?, 1, ?, 'importado_nac_priv', ?, ?, ?, ?, ?)""",
            (DOC_CORRECTO, desde, hasta, organismo,
             "Importado desde Nac_Priv (servicio anterior), tras corregir el DNI.", "Ariel",
             tipo, suma_apn, planta, motivo_baja),
        )
        registrar_auditoria(conn, "periodos_antiguedad", "INSERT", cur.lastrowid, None,
                             {"n_doc": DOC_CORRECTO, "fecha_desde": desde, "organismo": organismo}, "Ariel")

    # 3) período actual en el Ministerio (desde el contrato 1421 vigente)
    cur = conn.execute(
        """INSERT INTO periodos_antiguedad
               (n_doc, fecha_desde, fecha_hasta, organismo, cuenta_ascenso, observaciones,
                origen, usuario_carga, suma_apn)
           VALUES (?, ?, NULL, ?, 1, ?, 'importado_faltante', ?, 1)""",
        (DOC_CORRECTO, viejo["contrato_desde_1421"] or "2026-04-01", "Mtrio. Defensa",
         "Período actual, tras corregir el DNI.", "Ariel"),
    )
    registrar_auditoria(conn, "periodos_antiguedad", "INSERT", cur.lastrowid, None,
                         {"n_doc": DOC_CORRECTO, "fecha_desde": viejo["contrato_desde_1421"]}, "Ariel")

    # 4) título (Terciario, con diploma) -- marcado como título de grado porque el reporte de
    #    Access lo usa como tal para calcular la fecha de titulación / piso de cómputo
    cur = conn.execute(
        """INSERT INTO titulos (n_doc, id_niv, titulo, institucion, fecha_egreso, fecha_titulacion,
                                 es_titulo_grado, origen, observaciones)
           VALUES (?, 'T', 'Técnica en Gestión de Políticas Públicas', NULL, '2011-12-21', '2011-12-21',
                   1, 'importado_faltante',
                   'Título terciario (no universitario) marcado como título de grado a los efectos de este sistema, porque el reporte de Access lo usa como tal. Confirmar si esta equivalencia debe aplicarse a otros títulos terciarios del sistema.')""",
        (DOC_CORRECTO,),
    )
    registrar_auditoria(conn, "titulos", "INSERT", cur.lastrowid, None,
                         {"n_doc": DOC_CORRECTO, "titulo": "Técnica en Gestión de Políticas Públicas"}, "Ariel")

    # 5) marcar el registro viejo como duplicado erróneo (no se borra, se excluye del universo activo)
    conn.execute(
        """UPDATE agentes SET cuenta_1421=0, activo=0, motivo_clasif_1421=?, fecha_modif=?, usuario_modif=?
           WHERE n_doc=?""",
        (f"DUPLICADO ERRÓNEO: el DNI correcto de esta persona es {DOC_CORRECTO} (ver ese registro). "
         f"CONTRATADOS/Listado_1421 tenían mal cargado {DOC_VIEJO}.",
         datetime.now().isoformat(), "Ariel", DOC_VIEJO),
    )
    registrar_auditoria(conn, "agentes", "UPDATE", DOC_VIEJO, {"cuenta_1421": 1, "activo": 1},
                         {"cuenta_1421": 0, "activo": 0, "motivo": f"duplicado de {DOC_CORRECTO}, DNI incorrecto"},
                         "Ariel")

print("Corrección aplicada.")
