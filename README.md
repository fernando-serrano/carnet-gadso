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
- `test/` y archivos `test_*.py`: scripts y pruebas auxiliares.

## Arquitectura funcional

### Lectura y escritura de hojas

- Lectura de HOJA_BASE, HOJA_COMPARACION y HOJA_TERCERA por URL CSV publica.
- Escritura de observaciones/estados por Google Sheets API.

Regla clave:

- Lectura: CSV publico.
- Escritura: API de Sheets con cuenta de servicio.

### Validacion documental en Drive

- Se valida por DNI real en estructura de carpetas (raiz -> anio -> mes -> DNI).
- Se consideran documentos soportados: `.pdf`, `.png`, `.jpg`, `.jpeg`.
- Si no hay carpeta DNI o no hay documentos soportados, el registro se marca como error de tramite.

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

- Si el registro se completa: limpia observacion y registra fecha en comparacion.
- Si `HOLD_BROWSER_OPEN=1`, mantiene navegador abierto hasta interrupcion manual.

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
8. Escrituras realizadas en hojas.

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

Actualmente el flujo valida acceso y presencia de documentos en Drive por DNI.
La etapa de descarga de esos archivos y carga automatica en inputs tipo file de SUCAMEC no esta implementada aun en el flujo principal.
