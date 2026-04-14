# Flujo Emision de Carnet SUCAMEC

Este proyecto automatiza el flujo SEL de SUCAMEC con Playwright, OCR de captcha, cruce de Google Sheets, validacion de expedientes en Google Drive y trazabilidad detallada por logs.

## Objetivo del sistema

Procesar registros pendientes desde una hoja de comparacion y completar el tramite en SUCAMEC de forma controlada:

1. Leer fuentes remotas (Google Sheets por CSV).
2. Seleccionar un registro pendiente con reglas de negocio.
3. Validar expediente documental del DNI en Drive.
4. Ejecutar login y completar formulario en SUCAMEC.
5. Aplicar validaciones de alerta y escenarios de error.
6. Verificar secuencia de pago con fallback.
7. Escribir resultados en hojas (API de Sheets para escritura).

## Estructura del proyecto

Estructura principal observada en el workspace:

- `carnet_emision.py`: orquestador principal de todo el flujo.
- `carne_flow.py`: utilidades complementarias de flujo.
- `run_carnet_emision.bat`: launcher para Windows.
- `README.md`: documentacion funcional/tecnica.
- `requirements.md`: dependencias.
- `logs/`: logs por corrida.
- `data/`: cache y datos auxiliares.
- `secrets/carnet-drive-bot.json`: credenciales de cuenta de servicio.
- `test/`: scripts auxiliares de validacion.
- `test/alternos/`: validaciones experimentales o no criticas para el flujo base (por ejemplo, analisis de duplicados o pruebas aisladas de deteccion).

## Arquitectura funcional

### Lectura y escritura de hojas

- Lectura de HOJA_BASE, HOJA_COMPARACION y HOJA_TERCERA por URL CSV publica.
- Escritura de observaciones/estados por Google Sheets API.

Regla clave:

- Lectura: CSV publico.
- Escritura: API de Sheets con cuenta de servicio.

### Validacion documental en Drive

- Se valida por DNI real en estructura de carpetas `expedientes_carnet/{anio}/{mes}/{dni}`.
- Se consideran documentos soportados: `.pdf`, `.png`, `.jpg`, `.jpeg`.
- El flujo identifica y descarga localmente los adjuntos requeridos antes de abrir el formulario.
- Si no hay carpeta DNI o no hay documentos soportados, el registro se marca como `ERROR EN TRAMITE`.
- La confirmacion de carga no depende solo del input HTML: se valida por evidencia visual del componente PrimeFaces.

### Carga documental automatizada en SUCAMEC

El flujo actual completa la carga de adjuntos en el formulario con validaciones especificas por tipo de documento:

- Foto: archivo local descargado desde Drive, validado por extension y peso, confirmado por cambio en el `src` del preview.
- DJFUT: PDF local descargado desde Drive, validado por extension y peso, confirmado por texto visible del componente de upload o por `input.files`.
- Certificado medico: PDF local descargado desde Drive, validado por extension y peso, confirmado por texto visible del componente de upload o por `input.files`.
- Si el componente PrimeFaces devuelve error visible, el flujo registra la causa exacta y detiene el tramite.
- Si una carga falla, la observacion se enriquece con nombre de archivo y tamaño para trazabilidad inmediata.

### Interaccion web SUCAMEC

- Login con captcha OCR.
- Navegacion DSSP -> CARNE -> CREAR SOLICITUD.
- Llenado de campos principales y validaciones de growl.
- Verificacion de comprobante con fallback iterativo.

## Flujo operativo completo (paso a paso)

### 1) Arranque

1. Carga variables de entorno (`.env`).
2. Inicializa logger.
3. Confirma acceso a hojas con una sola linea por hoja:
   - `[HOJA_BASE] Acceso OK | filas=... | columnas=...`
   - `[HOJA_COMPARACION] Acceso OK | filas=... | columnas=...`
   - `[HOJA_TERCERA] Acceso OK | filas=... | columnas=...`

Nota:

- Ya no se imprime la muestra de 5 registros por hoja.  
- Ya no se hace prevalidacion inicial de Drive basada en esos 5 registros.

### 2) Cruce y seleccion de registro pendiente

1. Carga filas de base/comparacion/tercera hoja.
2. Filtra comparacion por estado objetivo configurable.
3. Cruza DNI con hoja base.
4. Resuelve:
   - sede objetivo por departamento,
   - modalidad por puesto,
   - tipo de documento por DNI.
5. Selecciona secuencias de pago candidatas (tercera hoja) con criterio estricto:
   - DNI vacio,
   - estado secuencia vacio,
   - excluye `USADO` y cualquier estado no vacio.

### 3) Login por grupo

1. Determina grupo (`JV` o `SELVA`) segun registro.
2. Ejecuta login con reintentos hasta `MAX_LOGIN_RETRIES_PER_GROUP`.
3. Si login falla definitivamente, se registra excepcion y se corta ese intento.

### 4) Validacion de expediente Drive por DNI (antes del formulario)

1. Busca carpeta DNI en Drive.
2. Lista archivos visibles.
3. Filtra extensiones soportadas.
4. Si valida correctamente, continua.
5. Si falla, registra en comparacion `ERROR EN TRAMITE` con observacion y termina ese registro.

### 5) Llenado de formulario SUCAMEC

Orden actual:

1. Sede.
2. Modalidad.
3. Tipo de registro (si vacio o fuera de objetivo, ajusta a `INICIAL`).
4. Tipo de documento.
5. Buscar por DNI.

### 6) Validaciones post-Buscar (alertas y escenarios)

Se ejecutan validaciones secuenciales con timeout corto configurable (`CARNET_POST_SEARCH_ALERT_WAIT_MS`, default 1200 ms):

1. `El documento ingresado no existe`.
2. `No puede sacar carnet ... porque ya cuenta con uno en distinta empresa`.
3. Subvalidacion de cambio de empresa:
   - si detecta `carne cesado`, o
   - si detecta `Este personal de seguridad ya cuenta con el carne nro. ...`,
   entonces cambia tipo a `CAMBIO DE EMPRESA` y reintenta Buscar.
4. `Registro en misma modalidad en estado OBSERVADO`.
5. `Prospecto no cuenta con curso vigente`.
6. Validacion de autocompletado para `INICIAL`:
   - exige valores en `Nombres`, `Apellido Paterno`, `Apellido Materno`.

Si cualquier validacion bloqueante falla:

- registra `ERROR EN TRAMITE` en hoja comparacion,
- escribe observacion textual,
- escribe responsable y fecha,
- termina el registro sin pasar a secuencias.

Si no se detecta una alerta bloqueante, el flujo descarga y carga Foto, DJFUT y Certificado medico desde Drive antes de continuar con la verificacion de secuencias.

### 7) Verificacion de secuencia de pago

1. Itera candidatos de secuencia.
2. Verifica recibo en SUCAMEC.
3. Deteccion multinivel de resultado:
   - etiqueta Monto/Fecha,
   - buffer growl JS,
   - growl en DOM,
   - texto en HTML.
4. Si secuencia es valida:
   - marca exito y finaliza.
5. Si `NO ENCONTRADO`:
   - limpia campo,
   - marca `NO ENCONTRADO` en tercera hoja,
   - continua con siguiente secuencia.
6. Si agota candidatos sin exito:
   - registra observacion en comparacion,
   - marca fracaso del registro.

### 8) Cierre

Secuencia actual de cierre transaccional:

1. Guardar solicitud en `createForm:botonGuardar`.
2. Actualizar hoja de comparacion a estado post-guardar (por defecto `POR TRAMSMITIR`) con responsable y fecha.
3. Marcar la secuencia en tercera hoja como `USADO`, registrando trazabilidad adicional:
   - `SOLICITADO POR=BOT CARNÉ SUCAMEC`
   - `DNI`
   - `APELLIDOS Y NOMBRE`
4. Navegar a Bandeja de Emision.
5. Aplicar filtro de estado (`CREADO` por defecto), ejecutar Buscar y seleccionar todos los resultados.
6. Accionar `Transmitir` en bandeja.
7. Confirmar el modal `Transmisión de registros` accionando el botón `Transmitir` del dialogo (`frmCompletarProceso:j_idt418`).
8. Recién después de la confirmación del modal, actualizar hoja de comparacion a:
   - `ESTADO_TRAMITE=TRANSMITIDO`
   - `OBSERVACION=Transmitido sin observaciones` (configurable)
   - responsable y fecha.
9. Ejecutar limpieza de cache local por DNI en `data/cache/upload_tmp/<dni>` (si esta habilitado).

Nota de performance:

- El nombre completo para tercera hoja se captura antes de Guardar para evitar esperas por lectura de DOM durante la redirección automática a bandeja.

Si `HOLD_BROWSER_OPEN=1`, mantiene navegador abierto hasta interrupcion manual.

## Validaciones implementadas

### Validaciones de acceso

- Acceso a hojas remotas (base, comparacion, tercera) con confirmacion minima por log.
- Acceso a Drive por expediente de DNI real.

### Validaciones de formulario

- Sede y modalidad contra opciones reales del dropdown.
- Tipo de registro valido (`INICIAL` o `CAMBIO DE EMPRESA`).
- Tipo de documento desde formato de DNI.

### Validaciones de alertas SUCAMEC

- Documento no existe.
- Ya cuenta con carnet con otra empresa (mensaje de distinta empresa).
- Carnet cesado.
- Ya cuenta con carnet nro. (gatilla cambio de empresa).
- Registro observado en misma modalidad.
- Curso no vigente.

### Validaciones de datos autocompletados

- Para `INICIAL`: nombres y apellidos deben venir autocompletados por SUCAMEC.

### Validaciones de comprobante

- Recibo encontrado / no encontrado con fallback por multiples fuentes de evidencia.

### Validaciones de adjuntos

- Foto: solo `.jpg` y `.jpeg`, con limite configurable de 80 KB por defecto.
- DJFUT: solo `.pdf`, con limite configurable de 80 KB por defecto.
- Certificado medico: solo `.pdf`, con limite configurable de 160 KB por defecto.
- Se valida extension y peso antes de intentar la carga al formulario.
- Se valida el resultado por señales visuales del componente y por el contenido del archivo asociado al input.
- Ante rechazo de carga, se registra el detalle en observacion y se clasifica el caso como `ERROR EN TRAMITE`.

## Excepciones y manejo de errores

Errores frecuentes y respuesta del sistema:

1. Credenciales faltantes:
   - aborta login del grupo con mensaje explicito.
2. Dependencias Google API faltantes:
   - lanza excepcion descriptiva para instalacion.
3. Carpeta DNI no encontrada en Drive:
   - registra `ERROR EN TRAMITE` en comparacion.
4. Sin documentos soportados en carpeta DNI:
   - registra `ERROR EN TRAMITE` en comparacion.
5. Alertas bloqueantes post-Buscar:
   - registra `ERROR EN TRAMITE` en comparacion.
6. Secuencias agotadas sin exito:
   - observacion en comparacion + corte de registro.
7. Fallo de login por captcha:
   - reintentos controlados por parametro.

## Escenarios funcionales cubiertos

### Escenario A: Registro INICIAL exitoso

- Buscar DNI sin alertas bloqueantes.
- Datos personales autocompletados.
- Secuencia valida.
- Resultado: registro completado.

### Escenario B: Carnet cesado

- Detecta alerta de cesado.
- Cambia a `CAMBIO DE EMPRESA`.
- Rebusca y continua flujo.

### Escenario C: Ya cuenta con carnet nro.

- Detecta alerta `ya cuenta con el carne nro`.
- Cambia a `CAMBIO DE EMPRESA`.
- Rebusca y continua flujo.

### Escenario D: Documento no existe / curso no vigente / observado

- Detecta alerta bloqueante.
- Marca `ERROR EN TRAMITE` en comparacion.
- No pasa a secuencias.

### Escenario E: Sin expediente valido en Drive

- No hay carpeta DNI o no hay archivos soportados.
- Marca `ERROR EN TRAMITE`.
- No intenta completar formulario final.

### Escenario F: Secuencia no encontrada

- Marca `NO ENCONTRADO` en tercera hoja.
- Toma siguiente secuencia candidata.

### Escenario G: Transmision en bandeja con confirmacion modal

- Ejecuta flujo de bandeja: Buscar -> seleccionar todos -> Transmitir.
- Confirma modal `dlgCompletarProceso` con el botón de transmisión.
- Actualiza estado final en comparacion solo tras esa confirmacion.

## Variables de entorno relevantes

### Credenciales SUCAMEC

- `TIPO_DOC`, `NUMERO_DOCUMENTO`, `USUARIO_SEL`, `CLAVE_SEL`
- `SELVA_TIPO_DOC`, `SELVA_NUMERO_DOCUMENTO`, `SELVA_USUARIO_SEL`, `SELVA_CLAVE_SEL`

### Fuentes de datos

- `CARNET_GSHEET_URL`
- `CARNET_GSHEET_COMPARE_URL`
- `CARNET_GSHEET_THIRD_URL`

### Drive

- `DRIVE_ROOT_FOLDER_ID`
- `DRIVE_CREDENTIALS_JSON`
- `DRIVE_VALIDATE_ON_START`

### Limites de adjuntos

- `CARNET_MAX_FOTO_BYTES`
- `CARNET_MAX_DJFUT_BYTES`
- `CARNET_MAX_CERT_MED_BYTES`

### Estados y cierre post-guardar

- `CARNET_ESTADO_POST_GUARDAR`
- `CARNET_OBSERVACION_POST_GUARDAR`
- `CARNET_BANDEJA_ESTADO_OBJETIVO`
- `CARNET_OBSERVACION_POST_TRANSMITIR`

### Mantenimiento de cache y logs

- `CARNET_CACHE_CLEAN_ON_SUCCESS`: limpia `data/cache/upload_tmp/<dni>` al cierre exitoso.
- `CARNET_LOG_SINGLE_FILE`: cuando es `1`, usa log único (`carnet_emision.log`).
- `CARNET_LOG_MAX_LINES`: umbral de truncado para log único (default 10000 líneas).
- `CARNET_LOG_ROTATING_KEEP_FILES`: en modo rotativo (`CARNET_LOG_SINGLE_FILE=0`), retiene solo N archivos por patrón y elimina los más antiguos.

### Ejecucion y tiempos

- `CARNET_ROW_BY_ROW`
- `CARNET_FORM_PRUEBA_ROWS`
- `MAX_LOGIN_RETRIES_PER_GROUP`
- `LOGIN_VALIDATION_TIMEOUT_MS`
- `CARNET_POST_SEARCH_ALERT_WAIT_MS`
- `CARNET_HEADLESS`
- `HOLD_BROWSER_OPEN`

### Modos especiales

- `CARNET_SHEET_CROSSCHECK_ONLY`
- `CARNET_SHEET_DEMO_ONLY`
- `DRIVE_VALIDATE_ONLY`

### Multiworker

- `RUN_MODE=scheduled`
- `SCHEDULED_MULTIWORKER=1`
- `SCHEDULED_WORKERS`
- `MULTIWORKER_CHILD`
- `WORKER_GROUP`
- `WORKER_ID`

## Modos de operacion

1. Fila por fila (default): procesa pendientes de forma individual.
2. Por grupo: ejecuta por grupo objetivo.
3. Programado multiworker: orquesta procesos por worker y grupo.

## Trazabilidad en logs

El log registra:

1. Acceso a hojas y volumen de datos.
2. Cruce (`COMP_FILA`, `BASE_FILA`, `TERCERA_FILA`).
3. Login y reintentos.
4. Validacion de expediente Drive por DNI y archivos detectados.
5. Selecciones de formulario (sede, modalidad, tipo registro, tipo documento).
6. Alertas detectadas y decisiones de cambio/error.
7. Verificacion de secuencias y resultado final.
8. Escrituras realizadas en hojas (comparacion y tercera hoja).
9. Flujo de bandeja y confirmacion de modal de transmisión.
10. Limpieza de cache local por DNI cuando el registro termina en transmitido.

Politica de logs implementada:

- Modo archivo único: si supera `CARNET_LOG_MAX_LINES`, se trunca al inicio de ejecución.
- Modo rotativo: se purgan archivos antiguos segun `CARNET_LOG_ROTATING_KEEP_FILES`, preservando siempre los más recientes.

## Instalacion

```bash
pip install -r requirements.md
python -m playwright install chromium
```

## Ejecucion

En Windows:

```bat
run_carnet_emision.bat
```

Directo con Python:

```bash
python carnet_emision.py
```

## Requisitos Google Cloud para escritura

1. Habilitar Google Sheets API en el proyecto de la cuenta de servicio.
2. Compartir hojas con `client_email` de la cuenta de servicio con rol Editor.
3. Configurar `DRIVE_CREDENTIALS_JSON` con la ruta correcta al JSON.

## Estado actual de carga documental

Actualmente el flujo valida acceso, localiza, descarga y carga automaticamente los documentos requeridos en el formulario de SUCAMEC.
La trazabilidad operativa queda reflejada en logs y en la hoja de comparacion, incluyendo el archivo afectado, su tamano y el motivo del rechazo cuando aplica.
Adicionalmente, el cierre de bandeja/transmision y la limpieza de cache local post-exito quedan registrados de forma explicita.
