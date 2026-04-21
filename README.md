# Flujo Emision de Carnet SUCAMEC

Automatizacion del flujo SEL de SUCAMEC con Playwright, OCR para captcha, cruce de Google Sheets, validacion documental en Google Drive y trazabilidad completa por logs.

## Estado actual (abril 2026)

- El modo operativo principal es scheduled multihilo.
- Se ejecutan workers en paralelo con reserva de filas para evitar colisiones.
- La lectura de Google Sheets tiene reintentos con backoff para tolerar cortes intermitentes.
- La validacion de alertas incluye estado OBSERVADO y estado TRANSMITIDO.
- Cada corrida scheduled crea su propia carpeta de logs (orquestador + workers + consola).

## Objetivo del sistema

Procesar registros pendientes desde hoja de comparacion hasta transmitirlos en bandeja SUCAMEC:

1. Leer hojas remotas (CSV publico).
2. Reservar un registro pendiente para un worker.
3. Validar expediente en Drive por DNI.
4. Completar formulario en CREAR SOLICITUD.
5. Validar alertas de negocio post-Buscar.
6. Reservar y validar secuencia de pago.
7. Guardar solicitud, transmitir en bandeja y actualizar hojas.

## Estructura del proyecto

- `app/carnet_emision.py`: flujo principal, orquestador y workers.
- `app/carne_flow.py`: utilidades de apoyo.
- `app/example.py`: flujo legacy/experimental conservado fuera de la raiz.
- `flows/runtime.py`: runtime compartido para abrir sesion, autenticar y cerrar recursos.
- `flows/login_flow.py`: bloque de autenticacion (login) aislado.
- `flows/formulario_flow.py`: bloque de acceso a CREAR SOLICITUD aislado.
- `flows/bandeja_flow.py`: bloque de acceso a BANDEJA DE EMISION aislado.
- `scripts/`: launchers reales y entrypoints segmentados.
- `INICIAR_CARNETS_SUCAMEC.bat`: launcher recomendado para usuarios.
- `run_scheduled.bat`, `run_carnet_emision.bat`: wrappers compatibles hacia `scripts/`.
- `docs/`: documentacion historica y notas de cambios.
- `README.md`: documentacion funcional y tecnica.
- `requirements.txt`: dependencias Python instalables.
- `requirements.md`: listado simple de dependencias, mantenido por compatibilidad.
- `.env.example`: plantilla portable sin secretos ni rutas locales absolutas.
- `logs/`: logs de ejecucion.
- `data/`: cache local y temporales.
- `secrets/carnet-drive-bot.json`: credenciales de cuenta de servicio.
- `test/`: scripts auxiliares.

## Instalacion en un dispositivo nuevo

Esta guia asume Windows y ejecucion desde la carpeta raiz del proyecto.

### 1) Preparar requisitos base

Instalar:

- Python 3.11 o superior.
- Git, si se descargara el proyecto desde repositorio.
- Acceso al archivo de credenciales Google Drive/Sheets de la cuenta de servicio.

Verificar Python:

```bash
python --version
```

### 2) Copiar o clonar el proyecto

Ubicar el proyecto en cualquier ruta del equipo. No es necesario que sea la misma ruta del equipo original.

Ejemplo:

```bat
cd C:\Automatizaciones
git clone <URL_DEL_REPOSITORIO> CARNET-GADSO
cd CARNET-GADSO
```

Si se copia manualmente, conservar la estructura de carpetas:

```txt
app/
flows/
scripts/
data/
secrets/
INICIAR_CARNETS_SUCAMEC.bat
requirements.txt
```

### 3) Crear entorno virtual

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
```

### 4) Instalar dependencias Python

```bash
pip install -r requirements.txt
```

### 5) Instalar navegador de Playwright

```bash
python -m playwright install chromium
```

### 6) Configurar `.env`

Crear `.env` desde la plantilla:

```bat
copy .env.example .env
```

Editar `.env` y completar:

- Credenciales SEL: `TIPO_DOC`, `NUMERO_DOCUMENTO`, `USUARIO_SEL`, `CLAVE_SEL`.
- Credenciales SELVA si aplica.
- URLs de Google Sheets: `CARNET_GSHEET_URL`, `CARNET_GSHEET_COMPARE_URL`, `CARNET_GSHEET_THIRD_URL`.
- Carpeta raiz de Drive: `DRIVE_ROOT_FOLDER_ID`.

Mantener rutas relativas para que el proyecto sea portable:

```env
EXCEL_PATH=data/programaciones-armas.xlsx
LOG_DIR=logs
DRIVE_CREDENTIALS_JSON=secrets/carnet-drive-bot.json
```

### 7) Instalar credenciales Google

Crear la carpeta `secrets` si no existe:

```bat
mkdir secrets
```

Colocar el JSON de la cuenta de servicio en:

```txt
secrets/carnet-drive-bot.json
```

La cuenta de servicio debe tener permisos sobre:

- Las hojas de Google Sheets usadas por el flujo.
- La carpeta raiz de Drive indicada en `DRIVE_ROOT_FOLDER_ID`.

### 8) Validar acceso antes de operar

Con el entorno virtual activo:

```bat
set DRIVE_VALIDATE_ONLY=1
python -m app.carnet_emision
set DRIVE_VALIDATE_ONLY=
```

Para probar solo login:

```bat
python scripts/run_login_flow.py --grupo JV
```

### 9) Ejecutar el flujo programado

La opcion recomendada es:

```bat
run_scheduled.bat
```

Cada corrida genera logs en:

```txt
logs/runs/scheduled_<timestamp>/
```

### 10) Notas de portabilidad

- No usar rutas absolutas tipo `C:\Users\...` dentro de `.env`.
- El codigo resuelve rutas relativas desde la raiz del proyecto.
- `INICIAR_CARNETS_SUCAMEC.bat` y `run_scheduled.bat` pueden quedarse en la raiz y delegan la ejecucion real a `scripts/run_scheduled.bat`.
- Si se mueve el proyecto a otra carpeta o equipo, solo deben acompañarlo `.env` y `secrets/carnet-drive-bot.json`.

## Arquitectura real de ejecucion

### 1) Orquestador scheduled multihilo

- Se activa con `RUN_MODE=scheduled` y `SCHEDULED_MULTIWORKER=1`.
- El orquestador crea hasta 4 workers en paralelo (`SCHEDULED_WORKERS`, limitado a 1..4).
- Cada worker se lanza como subproceso Python con variables de entorno propias:
  - `MULTIWORKER_CHILD=1`
  - `WORKER_ID`
  - `WORKER_RUN_ID`

### 2) Worker child

Cada worker ejecuta bucle continuo:

1. Busca candidatos en hoja comparacion.
2. Intenta reservar una fila escribiendo token en `ESTADO_TRAMITE`.
3. Procesa el registro completo (formulario + secuencia + bandeja).
4. Libera reserva de secuencia si aplica.
5. Continua hasta que no queden filas reservables.

### 3) Control de concurrencia por reservas

- Reserva de comparacion:
  - Token tipo `EN_PROCESO|RUN=...|W=...|DNI=...|TS=...`.
  - Verificacion de escritura para confirmar que el worker gano la reserva.
- Reserva de tercera hoja (secuencias):
  - Token tipo `RESERVADO|RUN=...|W=...|DNI=...|TS=...`.
  - Si una secuencia falla, se marca `NO ENCONTRADO` y se toma otra.
  - Si queda reserva colgada, se libera automaticamente cuando corresponde.
- Manejo de reservas expiradas:
  - Se soporta lease por tiempo para recuperar reservas antiguas.

## Flujo operativo del registro

### 1) Inicializacion

1. Carga `.env`.
2. Inicializa logger.
3. Confirma acceso a:
   - `HOJA_BASE`
   - `HOJA_COMPARACION`
   - `HOJA_TERCERA`

### 2) Cruce y preparacion

1. Cruza DNI de comparacion contra base.
2. Resuelve sede, modalidad y tipo de documento.
3. Determina grupo operativo (`JV` o `SELVA`).

### 3) Login y navegacion

1. Login con OCR captcha (con reintentos).
2. Navegacion DSSP -> CARNE -> CREAR SOLICITUD.
3. Confirmacion robusta de vista por campos reales del formulario (`createForm`).

### 4) Validacion de expediente Drive

Antes de llenar el formulario:

1. Ubica carpeta de DNI.
2. Verifica archivos soportados.
3. Descarga y prepara:
   - foto (`.jpg/.jpeg`)
   - DJFUT (`.pdf`)
   - certificado medico (`.pdf`)

Si falla, marca `ERROR EN TRAMITE` y termina el registro.

### 5) Llenado y busqueda por DNI

Orden operativo:

1. Sede.
2. Modalidad.
3. Tipo de registro (normaliza a `INICIAL` si corresponde).
4. Tipo de documento.
5. Ingreso de DNI y click en Buscar.

### 6) Validaciones post-Buscar

Se ejecutan con timeout corto configurable (`CARNET_POST_SEARCH_ALERT_WAIT_MS`):

1. Documento no existe.
2. Carnet vigente en distinta empresa.
3. Subvalidacion de cambio de empresa (carne cesado / ya cuenta con carne nro).
4. Misma modalidad en estado TRANSMITIDO.
5. Misma modalidad en estado OBSERVADO.
6. Prospecto sin curso vigente.
7. Para `INICIAL`, exige autocompletado de nombres y apellidos.

Si alguna alerta bloqueante aplica, se registra `ERROR EN TRAMITE` en comparacion.

### 7) Verificacion de secuencia

1. Worker reserva secuencia libre de tercera hoja.
2. Verifica en SUCAMEC con deteccion multinivel:
   - etiqueta Monto/Fecha
   - buffer growl JS
   - DOM growl
   - HTML completo
3. Resultado:
   - `ENCONTRADO`: continua.
   - `NO_ENCONTRADO`: marca tercera hoja y prueba siguiente.
   - `TIMEOUT`: criterio tolerante, asume exito para no bloquear falsos negativos.

### 8) Cierre transaccional

1. Guardar solicitud en `createForm:botonGuardar`.
2. Comparacion -> estado post-guardar (default `POR TRAMSMITIR`).
3. Tercera hoja -> secuencia `USADO` (+ trazabilidad DNI/nombre).
4. Navegacion a bandeja, filtro `CREADO`, seleccionar todos, transmitir.
5. Confirmacion de modal de transmision.
6. Comparacion -> `TRANSMITIDO` + observacion final.
7. Limpieza de cache local por DNI en `data/cache/upload_tmp/<dni>`.
8. Retorno a CREAR SOLICITUD para siguiente iteracion.

## Logging y trazabilidad

### Carpeta por corrida scheduled

`run_scheduled.bat` crea automaticamente:

- `logs/runs/scheduled_<timestamp>/run_scheduled_<timestamp>.log` (consola general).
- Log del orquestador dentro de la misma carpeta.
- Un archivo por worker: `worker_<id>_batch_<timestamp>.log`.

Esto se logra configurando `LOG_DIR` por corrida antes de ejecutar Python.

### Trazabilidad por worker

- En reservas y errores de tramite se registra responsable con tag de worker:
  - `BOT CARNE SUCAMEC W1`, `W2`, etc.
- Cada log de worker muestra DNI, fila de comparacion y fila de tercera hoja procesada.

### Politica de logs

- Modo archivo unico (`CARNET_LOG_SINGLE_FILE=1`): truncado por lineas con `CARNET_LOG_MAX_LINES`.
- Modo rotativo (`CARNET_LOG_SINGLE_FILE=0`): retencion por cantidad con `CARNET_LOG_ROTATING_KEEP_FILES`.

## Variables de entorno clave

### Ejecucion multihilo (obligatorio para produccion)

- `RUN_MODE=scheduled`
- `SCHEDULED_MULTIWORKER=1`
- `SCHEDULED_WORKERS=4`
- `SCHEDULED_PRELOAD_ITEMS_FOR_WORKERS=1` (si hay pocos registros, solo se levantan workers con trabajo)
- `CARNET_WORKER_SCAN_ROWS=200`
- `CARNET_WORKER_MAX_ROWS=0`

### Ventanas de workers (Windows)

- `CARNET_HEADLESS=1` para ejecutar sin mostrar ventanas de navegador.
- `CARNET_HEADLESS=0` para ejecutar con navegador visible solo cuando se necesite depurar.
- `BROWSER_TILE_ENABLE=1` para distribuir ventanas en mosaico.
- `BROWSER_TILE_ENABLE=0` para desactivar mosaico y evitar redimensionamiento/posicionamiento forzado.
- `BROWSER_START_MAXIMIZED=1` para maximizar ventanas visibles cuando el mosaico esta desactivado.
- Con precarga activa (`SCHEDULED_PRELOAD_ITEMS_FOR_WORKERS=1`), la cantidad de ventanas visibles depende de `workers_activos` (workers con items realmente asignados), no solo de `SCHEDULED_WORKERS`.

### Robustez de lectura y UI

- `CARNET_GSHEET_READ_RETRIES`
- `CARNET_GSHEET_TIMEOUT_SEC`
- `CARNET_GSHEET_RETRY_BASE_MS`
- `CARNET_CREAR_SOLICITUD_VALIDATION_TIMEOUT_MS`
- `CARNET_POST_SEARCH_ALERT_WAIT_MS`
- `CARNET_OCR_MAX_INTENTOS`

### Reservas y lease

- `CARNET_COMPARE_RESERVA_LEASE_MINUTES`
- `CARNET_COMPARE_ALLOW_STALE_IN_PROGRESS`
- `CARNET_TERCERA_RESERVA_LEASE_MINUTES`
- `CARNET_MAX_SECUENCIA_INTENTOS`

### Hojas y Drive

- `CARNET_GSHEET_URL`
- `CARNET_GSHEET_COMPARE_URL`
- `CARNET_GSHEET_THIRD_URL`
- `DRIVE_ROOT_FOLDER_ID`
- `DRIVE_CREDENTIALS_JSON` (puede ser relativa al proyecto, por ejemplo `secrets/carnet-drive-bot.json`)
- `CARNET_DRIVE_SEARCH_MAX_DEPTH=4` para buscar expedientes historicos en estructuras como `2026/04/DNI` o `2026/04/expedientes/DNI`.

### Estado y cierre

- `CARNET_ESTADO_POST_GUARDAR`
- `CARNET_OBSERVACION_POST_GUARDAR`
- `CARNET_BANDEJA_ESTADO_OBJETIVO`
- `CARNET_OBSERVACION_POST_TRANSMITIR`
- `CARNET_CACHE_CLEAN_ON_SUCCESS`

## Configuracion recomendada en .env

```env
RUN_MODE=scheduled
SCHEDULED_MULTIWORKER=1
SCHEDULED_WORKERS=4
CARNET_WORKER_SCAN_ROWS=200
CARNET_WORKER_MAX_ROWS=0

CARNET_CREAR_SOLICITUD_VALIDATION_TIMEOUT_MS=9000
CARNET_GSHEET_READ_RETRIES=6
CARNET_GSHEET_TIMEOUT_SEC=35
CARNET_GSHEET_RETRY_BASE_MS=800
CARNET_OCR_MAX_INTENTOS=6
```

## Ejecucion segmentada por funcionalidad

Permite revisar y depurar un dominio especifico sin lanzar todo el flujo transaccional.

### 1) Solo login

```bash
python scripts/run_login_flow.py --grupo JV
```

### 2) Login + acceso a formulario

```bash
python scripts/run_formulario_flow.py --grupo JV
```

### 3) Login + acceso a bandeja

```bash
python scripts/run_bandeja_flow.py --grupo JV
```

Opciones utiles:

- `--grupo SELVA` para probar credenciales del segundo grupo.
- `--keep-open` para dejar la sesion abierta al final.
- `CARNET_BANDEJA_ESTADO_OBJETIVO=CREADO` para aplicar filtro de estado al entrar a bandeja.

## Ejecucion

### Opcion recomendada (scheduled multihilo)

```bat
INICIAR_CARNETS_SUCAMEC.bat
```

### Opcion basica

```bat
run_carnet_emision.bat
```

### Opcion directa

```bash
python -m app.carnet_emision
```

## Modos especiales

- `CARNET_SHEET_CROSSCHECK_ONLY=1`: solo cruce de hojas.
- `CARNET_SHEET_DEMO_ONLY=1`: solo valida acceso a hojas.
- `DRIVE_VALIDATE_ONLY=1`: solo valida acceso a Drive.

## Requisitos Google Cloud

1. Habilitar Google Sheets API para la cuenta de servicio.
2. Compartir las hojas con el `client_email` de la cuenta con rol Editor.
3. Configurar ruta valida en `DRIVE_CREDENTIALS_JSON`. Se recomienda ruta relativa: `secrets/carnet-drive-bot.json`.

## Resumen operativo

El sistema esta preparado para operar en paralelo como estrategia principal, con control de colisiones por reservas, reintentos de red para Google Sheets, validaciones de negocio actualizadas (incluyendo estado TRANSMITIDO) y trazabilidad por worker de punta a punta.
