"""Simula 2 procesos (2 PCs) escribiendo casi al mismo tiempo sobre la
misma base, para probar que no se pierde ningún dato con el modo
DELETE + busy_timeout."""
import multiprocessing
import time
import operaciones as ops
from db import get_connection, verificar_integridad

TEST_DOC = 99999003


def limpiar():
    conn = get_connection()
    conn.execute("DELETE FROM auditoria WHERE registro_id=? OR valor_nuevo LIKE ?", (str(TEST_DOC), f'%{TEST_DOC}%'))
    conn.execute("DELETE FROM periodos_antiguedad WHERE n_doc=?", (TEST_DOC,))
    conn.execute("DELETE FROM config_agente WHERE n_doc=?", (TEST_DOC,))
    conn.execute("DELETE FROM agentes WHERE n_doc=?", (TEST_DOC,))
    conn.commit()
    conn.close()


def escritor(nombre_usuario, cantidad, barrera):
    import operaciones as ops2
    barrera.wait()  # todos arrancan lo más cerca posible al mismo tiempo
    for i in range(cantidad):
        ops2.cargar_periodo(TEST_DOC, f"20{10+i:02d}-01-01", f"20{10+i:02d}-06-01",
                             f"Organismo {nombre_usuario} {i}", True, "", nombre_usuario)


if __name__ == "__main__":
    limpiar()
    ops.crear_agente_manual(TEST_DOC, "PRUEBA CONCURRENCIA, Test", "setup")

    N_PROCESOS = 5
    POR_PROCESO = 4
    barrera = multiprocessing.Barrier(N_PROCESOS)
    procesos = [multiprocessing.Process(target=escritor, args=(f"usuario_{i}", POR_PROCESO, barrera))
                for i in range(N_PROCESOS)]

    t0 = time.time()
    for p in procesos:
        p.start()
    for p in procesos:
        p.join()
    t1 = time.time()

    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) c FROM periodos_antiguedad WHERE n_doc=?", (TEST_DOC,)).fetchone()["c"]
    conn.close()

    esperado = N_PROCESOS * POR_PROCESO
    print(f"Procesos simultáneos: {N_PROCESOS}, escrituras c/u: {POR_PROCESO}")
    print(f"Períodos esperados: {esperado}  |  Períodos guardados: {total}")
    print(f"Tiempo total: {t1 - t0:.2f}s")
    assert total == esperado, "¡SE PERDIERON ESCRITURAS!"
    print("OK: ninguna escritura se perdió con 5 'usuarios' simultáneos")

    ok, detalle = verificar_integridad()
    print("Integridad tras la prueba:", ok, detalle)
    assert ok

    limpiar()
    print("\nOK: prueba de concurrencia exitosa, base limpia")
