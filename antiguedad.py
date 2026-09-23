"""
antiguedad.py - Lógica de cómputo de antigüedad y ascensos de grado.

Regla de negocio (tal como la definió el usuario):
  * Un agente asciende UN (1) grado por cada TRES (3) años de
    antigüedad computable.
  * La antigüedad se evalúa a una fecha de corte (por defecto, el 31 de
    diciembre de cada año; se puede elegir cualquier otra fecha, por
    ejemplo para evaluar de cara a una renovación de contrato).
  * Si a la fecha de corte el agente acumuló un múltiplo de 3 años
    (computables) que no tenía un año antes de esa misma fecha, asciende
    con efecto a partir del día SIGUIENTE a la fecha de corte evaluada.
  * Ejemplo con el corte por defecto (31/12): ingresó 01/05/2023. Cumple
    3 años el 01/05/2026. Como recién se evalúa al 31/12/2026 (fecha en
    la que ya tiene 3 años y 8 meses), el ascenso corresponde a partir
    del 01/01/2027 (el día siguiente al corte).
  * Ejemplo con corte elegido a mano: si se evalúa al 15/01/2027 (por
    ejemplo, para decidir una renovación de contrato el 16/01/2027), y
    el agente cumple los 3 años en esa ventana, el ascenso corresponde
    a partir del 16/01/2027 (el día siguiente a esa fecha de corte).
  * Sólo cuentan los períodos de antigüedad marcados como
    cuenta_ascenso = 1, y sólo la porción de esos períodos que cae
    dentro de [fecha_inicio_conteo_grado, fecha_cierre_conteo] del
    agente (si están configuradas) y hasta la fecha de corte
    evaluada.

Todo el módulo trabaja con objetos `date` de Python y no hardcodea
ninguna base de datos: recibe listas de períodos ya leídas.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, List


@dataclass
class Periodo:
    fecha_desde: date
    fecha_hasta: Optional[date]  # None = abierto/vigente
    cuenta_ascenso: bool
    organismo: str = ""
    suma_apn: bool = True  # si suma para "Antigüedad en la Administración Pública Nacional"
    tipo_prestacion: str = ""


def _dias_periodo_hasta_corte(periodo: Periodo, fecha_corte: date,
                               inicio_conteo: Optional[date],
                               cierre_conteo: Optional[date]) -> int:
    """Días computables de un período, recortado por corte/inicio/cierre."""
    desde = periodo.fecha_desde
    hasta = periodo.fecha_hasta if periodo.fecha_hasta else fecha_corte

    if inicio_conteo and desde < inicio_conteo:
        desde = inicio_conteo
    if cierre_conteo and hasta > cierre_conteo:
        hasta = cierre_conteo
    if hasta > fecha_corte:
        hasta = fecha_corte

    if hasta < desde:
        return 0
    return (hasta - desde).days + 1  # inclusive


def antiguedad_computable_dias(periodos: List[Periodo], fecha_corte: date,
                                inicio_conteo: Optional[date] = None,
                                cierre_conteo: Optional[date] = None,
                                criterio: str = "cuenta_ascenso") -> int:
    """Suma los días computables de todos los períodos que cumplen el criterio
    indicado ('cuenta_ascenso' para el ascenso de grado 1421/02, o 'suma_apn'
    para la antigüedad total en la Administración Pública Nacional).

    Nota: si hay períodos superpuestos, cada día se cuenta UNA sola vez
    (se calcula por unión de intervalos, no por suma ingenua), para que
    dos períodos solapados no dupliquen antigüedad.
    """
    intervalos = _unir_intervalos(periodos, fecha_corte, inicio_conteo, cierre_conteo, criterio)
    return sum((hasta - desde).days + 1 for desde, hasta in intervalos)


def _unir_intervalos(periodos: List[Periodo], fecha_corte: date,
                      inicio_conteo: Optional[date] = None,
                      cierre_conteo: Optional[date] = None,
                      criterio: str = "cuenta_ascenso") -> List[tuple]:
    intervalos = []
    for p in periodos:
        incluir = p.cuenta_ascenso if criterio == "cuenta_ascenso" else p.suma_apn
        if not incluir:
            continue
        desde = p.fecha_desde
        hasta = p.fecha_hasta if p.fecha_hasta else fecha_corte
        if inicio_conteo and desde < inicio_conteo:
            desde = inicio_conteo
        if cierre_conteo and hasta > cierre_conteo:
            hasta = cierre_conteo
        if hasta > fecha_corte:
            hasta = fecha_corte
        if hasta >= desde:
            intervalos.append((desde, hasta))

    if not intervalos:
        return []

    intervalos.sort(key=lambda x: x[0])
    merged = [intervalos[0]]
    for desde, hasta in intervalos[1:]:
        ua, ub = merged[-1]
        if desde <= ub:
            merged[-1] = (ua, max(ub, hasta))
        else:
            merged.append((desde, hasta))
    return merged


def _meses_calendario(desde: date, hasta: date):
    """Descompone un intervalo [desde, hasta] (ambos inclusive) en años,
    meses y días EXACTOS de calendario (sin aproximar por 30 días), para
    no acumular error en antigüedades largas."""
    fin = hasta + timedelta(days=1)  # exclusivo, para restar como fecha de referencia
    y = fin.year - desde.year
    m = fin.month - desde.month
    d = fin.day - desde.day
    if d < 0:
        m -= 1
        # días del mes anterior a "fin"
        mes_prev = fin.month - 1 or 12
        anio_prev = fin.year if fin.month != 1 else fin.year - 1
        dias_mes_prev = [31, 29 if (anio_prev % 4 == 0 and (anio_prev % 100 != 0 or anio_prev % 400 == 0)) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes_prev - 1]
        d += dias_mes_prev
    if m < 0:
        y -= 1
        m += 12
    return y, m, d


def meses_computables(periodos: List[Periodo], fecha_corte: date,
                       inicio_conteo: Optional[date] = None,
                       cierre_conteo: Optional[date] = None,
                       criterio: str = "cuenta_ascenso") -> int:
    """Total de meses computables usando descomposición calendario exacta
    por intervalo (sin aproximar años/meses por división de días), y
    aplicando la regla de 'más de 15 días sueltos = 1 mes completo' UNA
    sola vez sobre el resto final de días acumulados."""
    intervalos = _unir_intervalos(periodos, fecha_corte, inicio_conteo, cierre_conteo, criterio)
    total_meses = 0
    total_dias_resto = 0
    for desde, hasta in intervalos:
        y, m, d = _meses_calendario(desde, hasta)
        total_meses += y * 12 + m
        total_dias_resto += d
    total_meses += total_dias_resto // 30
    resto_final = total_dias_resto % 30
    if resto_final > 15:
        total_meses += 1
    return total_meses


def dias_a_anios_meses_dias(total_dias: int):
    """Conversión aproximada (año=365.25 días, mes=30.44 días) sólo para
    mostrar un texto legible. El cómputo de grados usa años exactos
    (dias/365.25), no esta descomposición."""
    if total_dias <= 0:
        return 0, 0, 0
    anios = int(total_dias // 365.25)
    resto = total_dias - int(anios * 365.25)
    meses = int(resto // 30.44)
    dias = int(resto - meses * 30.44)
    return anios, meses, dias


def texto_antiguedad(total_dias: int) -> str:
    a, m, d = dias_a_anios_meses_dias(total_dias)
    partes = []
    if a:
        partes.append(f"{a} año{'s' if a != 1 else ''}")
    if m:
        partes.append(f"{m} mes{'es' if m != 1 else ''}")
    if d or not partes:
        partes.append(f"{d} día{'s' if d != 1 else ''}")
    return " ".join(partes)


def anios_exactos(total_dias: int) -> float:
    return total_dias / 365.25


def grados_por_antiguedad_meses(meses: int, grado_base: int = 0) -> int:
    """1 grado cada 3 años (36 meses) de antigüedad computable, más el grado base."""
    return grado_base + (meses // 36)


def evaluar_agente_anio(periodos: List[Periodo], anio: int,
                         inicio_conteo: Optional[date] = None,
                         cierre_conteo: Optional[date] = None,
                         grado_base: int = 0,
                         fecha_corte: Optional[date] = None,
                         grado_cargado: Optional[int] = None,
                         hoy: Optional[date] = None):
    """
    Evalúa a un agente al corte indicado (por defecto 31/12/`anio`), con
    efecto del ascenso el día siguiente al corte.

    `grados_acumulados` es el grado que le corresponde por antigüedad al
    corte. El grado de partida contra el que se compara depende del año:
      - Corte cuyo ascenso todavía no rige (año en curso o futuro) y con
        grado cargado: se parte del GRADO CARGADO, que es el que la persona
        tiene de verdad. Así, si tiene un grado mayor al que le corresponde
        (dado por error o conservado tras un cambio de tareas) no asciende
        hasta que la antigüedad lo supere; y si lo tiene menor (un ascenso
        que no se cargó) queda a la vista como pendiente en vez de perderse.
        Si el corte anterior tampoco rige todavía (proyección a más de un
        año), se asume que el ascenso intermedio se otorga.
      - Corte ya vigente (año cerrado) o sin grado cargado: no se sabe qué
        grado tenía en ese momento, así que se compara contra el grado que
        le correspondía por antigüedad un año antes.

    Devuelve un dict con todos los datos necesarios para persistir en
    `calculos_ascenso` y para mostrar en pantalla.
    """
    hoy = hoy or date.today()
    corte_actual = fecha_corte or date(anio, 12, 31)
    try:
        corte_anterior = corte_actual.replace(year=corte_actual.year - 1)
    except ValueError:
        # 29 de febrero en año no bisiesto -> usar 28/2
        corte_anterior = corte_actual.replace(year=corte_actual.year - 1, day=28)

    dias_actual = antiguedad_computable_dias(periodos, corte_actual, inicio_conteo, cierre_conteo)
    meses_actual = meses_computables(periodos, corte_actual, inicio_conteo, cierre_conteo)
    meses_anterior = meses_computables(periodos, corte_anterior, inicio_conteo, cierre_conteo)

    grados_actual = grados_por_antiguedad_meses(meses_actual, grado_base)
    grados_anterior = grados_por_antiguedad_meses(meses_anterior, grado_base)

    rige_corte_actual = corte_actual + timedelta(days=1) <= hoy
    rige_corte_anterior = corte_anterior + timedelta(days=1) <= hoy
    observacion = None
    pendiente = False

    if grado_cargado is None or rige_corte_actual:
        grado_partida = grados_anterior
    elif rige_corte_anterior:
        grado_partida = grado_cargado
        if grados_anterior > grado_cargado:
            pendiente = True
            # Buscar hacia atrás el primer corte en que ya correspondía más grado
            # del cargado: desde el día siguiente rige el ascenso no cargado.
            primer_corte = corte_anterior
            for _ in range(60):
                previo = primer_corte.replace(year=primer_corte.year - 1)
                meses_previo = meses_computables(periodos, previo, inicio_conteo, cierre_conteo)
                if grados_por_antiguedad_meses(meses_previo, grado_base) <= grado_cargado:
                    break
                primer_corte = previo
            pendiente_desde = primer_corte + timedelta(days=1)
            observacion = (f"Pendiente de carga: por antigüedad le corresponde grado {grados_anterior} "
                           f"desde el {pendiente_desde.strftime('%d/%m/%Y')} y tiene cargado {grado_cargado}.")
    else:
        grado_partida = max(grado_cargado, grados_anterior)

    if grado_cargado is not None and not rige_corte_actual and grado_cargado > grados_actual:
        observacion = (f"Tiene cargado grado {grado_cargado}, mayor al {grados_actual} que le corresponde "
                       f"por antigüedad: no asciende hasta superarlo.")

    asciende = grados_actual > grado_partida
    grados_nuevos = grados_actual - grado_partida if asciende else 0
    if not asciende:
        fecha_efectiva = None
    elif pendiente and grados_actual == grados_anterior:
        # No hay ascenso nuevo en este corte: sólo falta cargar uno que ya regía.
        fecha_efectiva = pendiente_desde
    else:
        fecha_efectiva = corte_actual + timedelta(days=1)

    return {
        "anio_evaluado": corte_actual.year,
        "antiguedad_computable_dias": dias_actual,
        "antiguedad_computable_texto": texto_antiguedad(dias_actual),
        "antiguedad_computable_anios": round(anios_exactos(dias_actual), 2),
        "grados_acumulados": grados_actual,
        "grados_anio_anterior": grado_partida,
        "asciende": asciende,
        "grados_nuevos": grados_nuevos,
        "fecha_efectiva_ascenso": fecha_efectiva.isoformat() if fecha_efectiva else None,
        "observacion": observacion,
    }
