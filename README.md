# Sistema de Antigüedad y Ascensos de Grado

Sistema para calcular automáticamente la antigüedad computable de cada
agente y determinar quién asciende de grado cada año, según la regla:

> **1 grado cada 3 años de antigüedad computable, evaluados al 31 de
> diciembre de cada año, con efecto a partir del 1° de enero del año
> siguiente.**

Construido en **Python + SQLite** por ser la combinación más robusta para
datos que no se pueden perder: transacciones ACID reales, un único
archivo portable, respaldo automático y auditoría completa de cada cambio.

## Correcciones aplicadas tras revisar contra el reporte de Access

Comparando ficha por ficha contra el reporte original de Access (caso de
prueba: POLLORA, Gisela — Documento 34.158.218), se corrigieron tres
problemas:

1. **Faltaban los períodos de antigüedad ANTERIORES al Ministerio**
   (ej. pasantías, otros organismos). Estaban en la tabla `Nac_Priv` de
   `Datos_Pers_2021.mdb` y no se habían importado. Ahora se importan
   (sólo para los 198 agentes del Decreto 1421/02), visibles en la
   ficha aunque no cuenten para el ascenso de grado.

2. **El Nivel y Grado mostrado era incorrecto.** Se estaba usando el de
   `Agentes_actual` (una escala general de personal), cuando el Nivel y
   Grado real del contrato 1421/02 está en `Listado_1421` (archivo
   `Contratados_1421_-_2345_-_PNUD__2026.mdb`). Se corrigió para los 198
   agentes, tomando el contrato más reciente de cada uno.

3. **La interfaz mostraba "948 agentes en el sistema"**, un número
   irrelevante para este programa. Ahora ningún listado ni mensaje
   menciona esa cifra: sólo se ve, se busca y se cuenta a los 198
   agentes del Decreto 1421/02. (Los datos de los demás siguen
   existiendo en la base por seguridad — nunca se borra nada — pero no
   aparecen en ningún lugar de la interfaz.)

Además se agregó el concepto de **fecha de corte oficial** (equivalente
a `Fecha_calculo_ant` de Access, hoy 31/12/2026): todas las fichas
calculan la antigüedad "al" esa fecha, igual que el reporte de Access,
en lugar de calcularla "a hoy". Se puede cambiar desde el menú
Sistema → "Cambiar fecha de corte oficial...".

La ficha ahora muestra, igual que el reporte de Access, **dos totales
distintos**:
- **Antigüedad en la Administración Pública Nacional**: suma todos los
  períodos (incluye pasantías y organismos anteriores).
- **Antigüedad para ascenso de grado — Decreto 1421/02**: sólo los
  períodos marcados "cuenta" (por defecto, sólo el período en el
  Ministerio).

No se calculó un tercer total de "Antigüedad ANSES" porque no se
encontró en los archivos originales una fuente de datos propia para
ese concepto — si tenés esa información en otro lado, decime y lo
agrego.

## Correcciones y mejoras (segunda vuelta de revisión)

1. **Buscador**: botón "Mostrar todos" para resetear la búsqueda y volver
   a ver la lista completa de agentes.
2. **Agentes faltantes corregidos**: se detectó que algunos agentes
   recién contratados (2025/2026) no estaban en `Agentes_actual`/
   `Antiguedad_LO` (las tablas usadas en la importación original), pero
   sí en `Listado_1421`, `CONTRATADOS` y `DPersonales`. Se reconstruyó
   la población completa desde la fuente correcta: **el sistema pasó de
   198 a 241 agentes**. Ver `migracion_agentes_faltantes.py`.
3. **Edición de datos del agente**: nuevo botón "Editar Nivel / Grado /
   Dependencia" en la ficha, y "Editar título" para el título de grado
   (institución, fecha de titulación, fecha de egreso). El "grado base
   de partida" en Configurar sigue siendo la forma de forzar a mano el
   punto de partida del cómputo de ascenso para un agente puntual.
4. **Botón "Contar grado desde la fecha de titulación"**: junto al
   título de grado, fija automáticamente la fecha de inicio de cómputo
   con esa fecha (con confirmación previa).
5. **Ascensos por año con fecha de corte editable**: además del año, se
   puede escribir cualquier fecha de corte (AAAA-MM-DD), no sólo 31/12.
6. **Fecha de corte automática**: ya no queda fija en una fecha
   hardcodeada. Por defecto es siempre "31/12 del año actual" y se
   actualiza sola. Se puede fijar una fecha manual desde el menú
   Sistema (por ejemplo para simular un cierre distinto) y volver a la
   automática cuando se quiera.
7. Se quitó la línea "Contrato 1421 vigente" de la ficha y el comentario
   sobre la antigüedad ANSES.
8. **Usuario recordado por PC**: el nombre ingresado se guarda en un
   archivo local (`data/usuario_local.txt`, NO en la base compartida).
   La próxima vez saluda "Hola, [nombre]. ¡Bienvenido/a!" con botones
   "Ingresar" y "Cambiar usuario" (también disponible desde el menú
   Sistema en cualquier momento).

## Filtro por Decreto 1421/02

El sistema fue ajustado para que **sólo cuenten los agentes contratados
en el marco del Decreto 1421/02**. La clasificación se hizo cruzando:

1. Los documentos que aparecen en las tablas de origen del régimen 1421
   (`Listado_1421`, `Historico 1421`, `1421 discriminado por nivel`, `ASU`
   del archivo `Contratados_1421_-_2345_-_PNUD__2026.mdb`) → columna
   `vinculado_1421`.
2. El campo **`Fecha de baja`** de la tabla `CONTRATADOS` (mismo archivo)
   → columna `tiene_baja_1421`. Si tiene una fecha de baja registrada,
   se excluye.
3. `cuenta_1421 = 1` sólo si está vinculado **y no** tiene fecha de baja.

Resultado sobre los datos actuales:

| | Cantidad |
|---|---|
| Total de agentes en el sistema | 948 |
| Vinculados a alguna tabla de origen 1421 | 342 |
| — de esos, con fecha de baja (excluidos) | 144 |
| No vinculados a 1421 (excluidos) | 606 |
| **Cuentan para el sistema (`cuenta_1421=1`)** | **198** |

**Todos los reportes (búsqueda de agentes, listado de ascensos por año,
exportación a Excel) filtran por `cuenta_1421=1` por defecto.** Nadie fue
borrado: los 750 agentes restantes siguen en la base, sólo que no
aparecen en las consultas por defecto. Se puede consultar el motivo
exacto de la clasificación de cualquier persona desde la opción 11 del
menú, o pasando `solo_1421=False` a las funciones de `operaciones.py`
para ver el universo completo.

Si en algún momento cambia la fuente de datos (nuevos contratos, nuevas
bajas), correr de nuevo:

```bash
python migracion_1421.py <Listado_1421.csv> <Historico_1421.csv> \
    <1421_discriminado_por_nivel.csv> <ASU.csv> <CONTRATADOS.csv> --usuario "Ariel"
```

Es idempotente: se puede correr las veces que haga falta, siempre
recalcula la clasificación completa dentro de una transacción con backup
previo.

## Por qué es robusto (punto por punto)

1. **Nunca se pierde nada al guardar.** Cada operación de escritura corre
   dentro de una transacción real (`BEGIN IMMEDIATE ... COMMIT`). Si algo
   falla a mitad de camino, se hace `ROLLBACK` completo: o se guarda todo,
   o no se guarda nada. Esto está probado en `test_sistema.py` (punto 9),
   forzando un error real y verificando que no quedó ningún registro a
   medio insertar.
2. **Respaldo automático antes de cada cambio.** Antes de cualquier
   escritura, se copia el archivo `.db` completo a `/backups` con
   timestamp. Si algo saliera mal igual, siempre hay una copia intacta
   del momento anterior. Los backups nunca se borran automáticamente.
3. **Nada se borra físicamente.** "Eliminar" un período es un
   soft-delete: la fila queda en la base con `activo=0`. El dato nunca
   desaparece.
4. **Auditoría total.** La tabla `auditoria` registra cada INSERT/UPDATE/
   SOFT_DELETE con el valor anterior y el nuevo (en JSON), quién lo hizo
   y cuándo. Es un historial inmutable.
5. **`PRAGMA foreign_keys=ON`** evita cargar antigüedad de un agente que
   no existe. **`journal_mode=WAL`** + **`synchronous=FULL`** hacen que la
   base resista un corte de luz o un cierre abrupto sin corromperse.
6. **Verificación de integridad** disponible en cualquier momento
   (`PRAGMA integrity_check`, opción 9 del menú).
7. **Doble respaldo**: además del `.db`, `exportar.py backup_csv` vuelca
   todas las tablas a CSV plano, legible sin ningún programa especial.

## Instalación y uso (con ventana, sin comandos)

**Paso 1 (una sola vez):** instalar Python desde https://www.python.org/downloads/
(al instalar, tildar la casilla "Add python.exe to PATH" / "Add Python to PATH").

**Paso 2 (una sola vez):** doble clic en **`Instalar (una sola vez).bat`**
(Windows) o **`Instalar (una sola vez).command`** (Mac). Instala lo
necesario automáticamente.

**Paso 3 (cada vez que se quiera usar):** doble clic en
**`Iniciar Sistema.bat`** (Windows) o **`Iniciar Sistema.command`** (Mac).
Se abre una ventana con pestañas: "Agentes" y "Ascensos por año", con
botones para cada operación — no hace falta escribir ningún comando.

## Uso por línea de comandos (opcional, para uso avanzado)

Requiere Python 3.9+ (sin dependencias externas para el uso normal;
`openpyxl` sólo hace falta para exportar a Excel).

```bash
pip install openpyxl
python cli.py
```

Menú interactivo con las mismas opciones que la ventana, para quien
prefiera trabajar por terminal.

| Opción | Qué hace |
|---|---|
| 1 | Ver la ficha completa de un agente: antigüedad, períodos, título de grado, configuración |
| 2 | Cargar un nuevo período de antigüedad |
| 3 | Modificar un período previo |
| 4 | Marcar si un período cuenta o no para el ascenso |
| 5 | Fijar la fecha desde la que se cuenta el grado y/o la fecha de cierre, por agente |
| 6 | Desactivar un período (soft-delete, no se borra) |
| 7 | Crear un agente nuevo |
| 8 | Ver quiénes ascienden en un año determinado (con fecha efectiva) |
| 9 | Verificar integridad de la base y ver backups disponibles |
| 10 | Backup manual inmediato |

## Exportar a Excel / CSV

```bash
python exportar.py ascensos 2026     # listado de quiénes ascienden, en .xlsx
python exportar.py backup_csv        # respaldo completo legible en CSV
```

## Estructura de datos

- **`agentes`**: ficha básica (documento, nombre, nivel/grado actuales).
- **`periodos_antiguedad`**: cada tramo de antigüedad de un agente
  (fecha desde, fecha hasta u "vigente", organismo, y si **cuenta o no**
  para el ascenso). Un agente puede tener varios períodos con criterios
  distintos — es la solución al problema de "cada agente puede tener un
  criterio diferente".
- **`config_agente`**: por agente, la fecha desde la que se debe contar
  el grado (si es distinta de sus períodos), la fecha de cierre de
  cómputo, y un grado base de partida si no arranca en 0.
- **`titulos`**: títulos de cada agente; los universitarios
  (`id_niv = 'U'`) se marcan como **título de grado** y aparecen
  destacados en la ficha.
- **`calculos_ascenso`**: historial de cada corrida de cálculo guardada
  (para poder demostrar, a futuro, "qué dijo el sistema" en cada corte).
- **`auditoria`**: bitácora inmutable de todos los cambios.

## Datos ya importados

Se importó desde `Datos_Pers_2021.mdb` (tablas `Agentes_actual`,
`Antiguedad_LO`, `Agente_titulo`):

- 948 agentes
- 453 períodos de antigüedad (importados como período único vigente por
  agente, marcado "cuenta" por defecto — a revisar/dividir caso por caso
  donde corresponda un criterio distinto)
- 1173 títulos

**Importante:** los datos importados de `Antiguedad_LO` traían la fecha
de antigüedad ya consolidada del sistema anterior (`F_alta`), pero **no
distinguían qué parte de esa antigüedad debía o no contar para el
ascenso de grado**. Por eso se importó todo marcado como "cuenta" por
defecto: es el punto de partida más fiel a los datos originales, pero
se recomienda revisar agente por agente (opción 1 y 4 del menú) para
ajustar los casos con criterio distinto.

## Uso simultáneo desde varias PCs (carpeta compartida en red)

Toda la información vive en **un único archivo**: `data/antiguedad.db`.
Si esta carpeta está en una red compartida, varias PCs pueden abrir el
programa y ver los mismos datos.

**Uso ocasional simultáneo** (dos personas guardan casi al mismo
momento, de vez en cuando) está soportado:
- La base usa el modo clásico de SQLite (`journal_mode=DELETE`) en vez
  de WAL, porque WAL depende de archivos auxiliares con memoria
  compartida que no son confiables en carpetas de red (SMB/Windows) —
  es una limitación conocida y documentada del propio SQLite, no de
  este programa.
- `busy_timeout=15000`: si dos personas guardan a la vez, la segunda
  espera hasta 15 segundos en silencio a que termine la primera, en
  vez de arriesgar el archivo. Probado con `test_concurrencia.py`: 5
  "usuarios" guardando exactamente al mismo tiempo, cero escrituras
  perdidas.
- Si el tiempo de espera se agota (alguien tarda MUCHO en guardar, muy
  poco probable), aparece un mensaje claro: "La base está siendo usada
  por otra persona en este momento. Esperá unos segundos y probá de
  nuevo." — nunca se pierde el dato silenciosamente ni se corrompe el
  archivo, en el peor caso hay que reintentar.

**Lo que este esquema NO cubre bien**: uso simultáneo intenso y
constante (muchas personas guardando todo el día, todo el tiempo, al
mismo momento). Para ese escenario hace falta una base de datos
"cliente-servidor" de verdad (por ejemplo, un pequeño servidor central
al que todas las PCs se conecten por red), que es una arquitectura
distinta a la actual. Si el uso real termina siendo más intenso de lo
esperado, avisar para migrar a ese esquema.

## Caso puntual corregido: ALFONZO, Yésica Lorena (DNI)

**Las dos bases de Access tenían un DNI distinto para la misma persona**:
`CONTRATADOS`/`Listado_1421` traían `29.946.105`, mientras que
`DPersonales`/`Nac_Priv`/`Agente_titulo` (donde estaban sus períodos y
título reales) traían `29.946.405` — el correcto, confirmado con el
reporte real de Access. Como la importación cruza todo por número de
documento exacto, nunca encontró sus datos.

Se verificó que es un **caso aislado** (se compararon los 241 nombres
del sistema contra `DPersonales` por nombre normalizado, sin más
discrepancias). Se corrigió creando el registro con el DNI correcto
(`correccion_dni_alfonzo.py`), con sus 2 períodos previos en la
Secretaría General de la Presidencia y su período actual en el
Ministerio, y se marcó el registro viejo (`29946105`) como duplicado
erróneo (`cuenta_1421=0`, sin borrarlo). Verificado contra el reporte
de Access: coincide (APN exacto, 1421 con la misma diferencia cosmética
de 1-2 días que ya se explicó para POLLORA, sin afectar el cálculo real
de grados).

**Hallazgo pendiente de confirmar**: su título es *Terciario* (`T`),
no *Universitario* (`U`), pero el reporte de Access lo trata igual que
un título de grado a los efectos del piso de cómputo para Nivel A/B.
Por ahora sólo se marcó así para este caso puntual. Si hay más agentes
con títulos terciarios que deberían tratarse igual, avisar para
extender la regla a todo el sistema (hoy sólo cuentan los `id_niv='U'`).

**Actualización — confirmado por Ariel**: los títulos terciarios
(`id_niv='T'`) sí cuentan como título de grado en todo el sistema, no
sólo para este caso. Se aplicó de forma general: **95 títulos**
terciarios marcados como título de grado, lo que hizo que a **9
agentes** Nivel A/B más se les fijara automáticamente su fecha de
titulación como piso de cómputo (antes no tenían ningún título
reconocido). Los Nivel A/B sin título de grado bajaron de 13 a **3**
(CARBALLO, FIONDA, GARCIA CAMARA) — genuinamente sin título cargado,
pendientes de revisión.

## Dos bugs importantes corregidos (agosto 2026)

**1) 103 agentes vigentes no aparecían en "Ascensos por año".** La
importación original marcó `activo=0` a cualquier agente que no
estuviera en la tabla `Agentes_actual` de Access, sin relación con si
realmente seguía trabajando. Como el filtro de "Ascensos por año" (y el
total de "contratados activos") excluye a los inactivos, esos 103
agentes vigentes (con `cuenta_1421=1`, es decir sin baja registrada)
quedaban invisibles en ambos lugares — el "Total de contratados
activos" mostraba 138 en vez de 241. Se corrigió sincronizando
`activo=1` para todos los que tienen `cuenta_1421=1` (que es la fuente
de verdad real de "sigue vigente"). Hay una prueba automática
(`test_sistema.py`, punto 12) que impide que esto vuelva a pasar sin
que falle la suite de pruebas.

**2) La columna "¿APN?" estaba mal para la mayoría de los períodos
anteriores.** El campo `suma_ant` que traía `Nac_Priv` de Access no
reflejaba la regla real, y hasta estaba invertido para el tipo `Priv`
(20 de 22 períodos privados sumaban a APN, cuando no deberían). Regla
confirmada por la Dirección: **toda la antigüedad cuenta para
Administración Pública Nacional, excepto los períodos tipo `Priv`**
(no depende del nivel, a diferencia de la regla de ascenso de grado).
Se corrigió con `ops.aplicar_regla_apn_por_tipo(usuario)` — revisó 330
períodos, corrigió 268. También hay una prueba automática que lo
protege (`test_sistema.py`, punto 13).

Ambas correcciones están disponibles para volver a correr desde el
menú Sistema → "Recalcular reglas automáticas..." (ahora incluye las
tres reglas: fecha de titulación para A/B, tipo de período para el
ascenso 1421, y tipo de período para APN).

## Regla de qué antigüedad previa cuenta para el ascenso (por nivel y tipo)

**Corrección importante (agosto 2026)**: al importar los períodos
anteriores desde `Nac_Priv`, se había asumido por error que NINGUNO
contaba para el ascenso de grado 1421 (basado en un solo caso
validado, una pasantía). Eso estaba mal para la mayoría de los casos.

La regla real, confirmada por la Dirección:

- **Niveles C, D, E**: cuenta TODA la antigüedad anterior para el
  ascenso de grado 1421, **excepto** los períodos de tipo `Priv`
  (sector privado).
- **Niveles A, B**: cuenta TODA la antigüedad anterior **excepto**
  `Priv` y `Pas` (pasantía), pero sólo a partir de la fecha del título
  de grado (ver la regla de arriba).

Se corrigió con `ops.aplicar_regla_tipo_periodo_por_nivel(usuario)` —
revisó 330 períodos, corrigió 281. Se puede volver a correr en
cualquier momento desde el menú Sistema → "Recalcular reglas
automáticas..." (por ejemplo, después de cargar agentes o períodos
nuevos). Es no-destructiva: sólo cambia `cuenta_ascenso` según la
regla, con auditoría de cada cambio, y nunca toca los períodos
cargados a mano ni el período actual del Ministerio.

**5 agentes no tienen Nivel cargado** y por eso sus períodos anteriores
quedaron sin tocar (ni a favor ni en contra) — conviene revisarlos a
mano y completarles el Nivel; después correr la regla de nuevo desde
el menú.

## Total de contratados activos y exportación completa

En la pestaña Agentes, abajo del buscador, se ve el **total de
contratados activos** (Decreto 1421/02, sin fecha de baja). El botón
"Exportar listado a Excel" genera un archivo con todos ellos: nivel,
grado, dependencia, título, fecha de titulación, y los dos totales de
antigüedad (ascenso 1421 y Administración Pública Nacional).

## Regla automática para Nivel A y B (fecha de titulación)

Para agentes de Nivel A o B, si no se configuró una fecha de inicio de
cómputo a mano, el sistema usa automáticamente la fecha de titulación
del título de grado como punto de partida para el ascenso. Se aplica
sólo:
- al editar el Nivel de un agente a A o B,
- al cargar o editar su título de grado,
- o ejecutando `ops.aplicar_default_titulacion_ab_todos(usuario)` para
  todos los agentes de una vez.

**Nunca pisa una fecha ya configurada a mano** — si el campo "Fecha
inicio de conteo" ya tiene algo cargado, la regla no lo toca; hay que
borrarlo primero si se quiere que vuelva a aplicar el automatismo.

Esta regla ya se aplicó una vez a los 241 agentes existentes (agosto
2026): a **81 agentes** de Nivel A/B que no tenían una fecha configurada
y sí tenían título de grado con fecha de titulación, se les fijó esa
fecha como inicio de cómputo. Esto cambió el resultado de antigüedad
computable de esos 81 agentes (por ejemplo, POLLORA — el caso usado
para validar el sistema contra el reporte de Access — pasó de "13 años
8 meses 1 día" a "12 años 29 días", porque antes contaba desde su fecha
de ingreso al Ministerio y ahora cuenta desde su fecha de titulación).
**Recomendación**: antes de usar el sistema para una decisión de
ascenso real, revisar agente por agente que la fecha aplicada sea la
que corresponde según el criterio vigente — se puede corregir a mano en
cualquier momento desde "Configurar fechas / grado base", y todo queda
registrado en la auditoría (se puede reconstruir el valor anterior si
hace falta revertir).

## Alta manual de agentes (nuevo criterio de carga)

La Dirección va a dejar de cargar datos desde Access y va a cargar todo
a mano de acá en adelante. Para eso:

1. Botón **"+ Crear agente nuevo"** (pestaña Agentes): documento,
   nombre, nivel, grado y dependencia.
2. Con el agente ya creado y seleccionado, usar **"Cargar período
   nuevo"** para su antigüedad, y **"Editar título"** para su título de
   grado.
3. Si es Nivel A o B y se cargó un título con fecha de titulación, el
   sistema fija sólo la fecha de inicio de cómputo (ver regla arriba) —
   se puede corregir después con "Configurar fechas / grado base" si
   corresponde otro criterio para ese agente en particular.

## Pruebas automáticas

```bash
python test_sistema.py
```

Verifica: integridad de la base, el ejemplo exacto que diste (ingreso
01/05/2023 → ascenso efectivo 01/01/2027), que un período marcado "no
cuenta" no suma antigüedad, que la fecha de cierre limita el cómputo,
que el soft-delete no borra datos, y que un error a mitad de una
escritura no deja nada guardado a medias (rollback real).

## Archivos

```
sistema_antiguedad/
├── schema.sql          Esquema de la base de datos
├── db.py               Conexión, transacciones, backups, auditoría
├── antiguedad.py        Lógica de cómputo de antigüedad y ascensos
├── operaciones.py       Operaciones de negocio (consultas y escrituras)
├── cli.py               Menú interactivo
├── exportar.py           Exportación a Excel y backup CSV
├── importar_datos.py     Importación inicial (ya ejecutada)
├── test_sistema.py       Pruebas automáticas
├── data/antiguedad.db     Base de datos (NO subir a repos públicos: datos personales)
├── backups/              Copias de seguridad automáticas
└── exports/              Reportes generados
```
