# Flujo Emision de Carnet SUCAMEC

Este proyecto automatiza el flujo SEL de SUCAMEC para emision de carnet con Playwright, OCR de captcha, cruce de Google Sheets, validacion en Drive y registro detallado por logs.

## Resumen funcional

El proceso completo hace lo siguiente:

1. Lee hojas de Google Sheets (base, comparacion, tercera hoja) por export CSV.
2. Cruza DNI pendientes contra hoja base.
3. Selecciona sede, modalidad y tipo de documento segun reglas de negocio.
4. Ingresa DNI y ejecuta Buscar en el formulario.
5. Si detecta carné cesado, cambia tipo de registro a CAMBIO DE EMPRESA y reintenta Buscar.
6. Valida comprobante (copia de secuencia de pago) con fallback iterativo.
7. Si la secuencia no existe, marca NO ENCONTRADO en tercera hoja y prueba la siguiente disponible.
8. Si la secuencia es valida, cierra el intento y marca el registro como completado.

## Estructura principal

- carnet_emision.py: orquestador principal de login, formulario, hojas y drive.
- run_carnet_emision.bat: launcher para Windows.
- logs/: trazas por ejecucion.
- data/: datos auxiliares.
- secrets/: credenciales de cuenta de servicio (Drive/Sheets).
- test/: pruebas auxiliares.

## Flujo detallado paso a paso

### 1) Inicializacion

- Carga variables de entorno con dotenv.
- Inicializa logger (archivo unico o por corrida segun configuracion).
- Opcionalmente imprime muestra de las hojas para trazabilidad.

### 2) Lectura de fuentes remotas

- HOJA_BASE: datos fuente (DNI, departamento, puesto, etc.).
- HOJA_COMPARACION: filtro de pendientes por estado.
- HOJA_TERCERA: banco de secuencias de pago.

La lectura se hace por URL CSV publica. No requiere API para leer.

### 3) Prevalidacion Drive

- Valida acceso a carpeta raiz.
- Verifica si existe carpeta por DNI.
- Lista nombres visibles de documentos por DNI.

### 4) Cruce y seleccion del registro a procesar

- Aplica criterio de estados objetivo en hoja de comparacion.
- Cruza DNI con hoja base.
- Resuelve metadatos del formulario:
	- sede objetivo por departamento.
	- modalidad por puesto.
	- tipo de documento por formato de DNI.
- Toma secuencias candidatas desde tercera hoja con criterio estricto:
	- DNI vacio.
	- ESTADO_SECUENCIA_PAGO vacio.
	- excluye estado USADO y cualquier estado no vacio.

### 5) Login y navegacion en SUCAMEC

- Abre Chromium con Playwright.
- Navega a login tradicional.
- Completa credenciales por grupo (JV o SELVA).
- Resuelve captcha con OCR.
- Valida login por señales UI.
- Navega menu DSSP -> CARNE -> CREAR SOLICITUD.

### 6) Llenado de formulario (orden actual restaurado)

Orden exacto de trabajo:

1. Seleccionar sede.
2. Seleccionar modalidad.
3. Validar tipo de registro (si vacio, coloca INICIAL).
4. Seleccionar tipo de documento.
5. Ingresar documento (DNI) y hacer Buscar.
6. Subvalidacion de carné cesado:
	 - si hay mensaje de carné cesado, cambia a CAMBIO DE EMPRESA.
	 - vuelve a ejecutar Buscar con el mismo DNI.
7. Recién despues entra al loop de secuencias de pago.

### 7) Verificacion de comprobante y fallback

Por cada secuencia candidata:

- Loguea intento con secuencia y fila real de tercera hoja (TERCERA_FILA).
- Ingresa secuencia y pulsa Verificar.
- Evalua resultado con deteccion multinivel:
	- etiqueta de exito Monto/Fecha (validacion positiva fuerte).
	- growl en buffer JS.
	- growl en DOM.
	- texto en HTML como respaldo.
- Si es valida:
	- registra [OK] y finaliza loop.
- Si es NO ENCONTRADO:
	- limpia campo comprobante.
	- intenta marcar NO ENCONTRADO en tercera hoja (misma fila).
	- continua con siguiente secuencia.

Si no encuentra ninguna secuencia valida, deja observacion en hoja comparacion y marca fracaso del registro.

## Reglas de actualizacion en Google Sheets

Se actualiza por API solo cuando hay escritura:

- HOJA_COMPARACION:
	- observacion.
	- fecha tramite.
- HOJA_TERCERA:
	- estado secuencia de pago (ej. NO ENCONTRADO).

Nota:

- Lectura: via CSV (sin API).
- Escritura: via Google Sheets API (si requiere API habilitada + permisos).

## Variables de entorno clave

### Credenciales SEL

- TIPO_DOC / NUMERO_DOCUMENTO / USUARIO_SEL / CLAVE_SEL.
- SELVA_TIPO_DOC / SELVA_NUMERO_DOCUMENTO / SELVA_USUARIO_SEL / SELVA_CLAVE_SEL.

### Hojas

- CARNET_GSHEET_URL.
- CARNET_GSHEET_COMPARE_URL.
- CARNET_GSHEET_THIRD_URL.
- CARNET_SHEET_PRINT_SAMPLE.
- CARNET_SHEET_SAMPLE_ROWS.

### Drive y API

- DRIVE_ROOT_FOLDER_ID.
- DRIVE_CREDENTIALS_JSON.
- DRIVE_VALIDATE_ON_START.

### Ejecucion

- CARNET_ROW_BY_ROW.
- CARNET_FORM_PRUEBA_ROWS.
- MAX_LOGIN_RETRIES_PER_GROUP.
- LOGIN_VALIDATION_TIMEOUT_MS.
- CARNET_HEADLESS.
- HOLD_BROWSER_OPEN.

### Modos especiales

- CARNET_SHEET_CROSSCHECK_ONLY.
- CARNET_SHEET_DEMO_ONLY.
- DRIVE_VALIDATE_ONLY.

### Orquestacion multiworker

- SCHEDULED_MULTIWORKER=1.
- SCHEDULED_WORKERS (1 a 4).

## Modos de operacion

- Modo fila por fila (default): procesa pendientes uno por uno con su propio ciclo de login.
- Modo por grupos: ejecuta por JV/SELVA sin amarrar a fila individual.
- Modo multiworker: orquesta subprocesses por grupo con logs separados.

## Trazabilidad en logs

El log deja evidencia de:

- Cruce de filas (COMP_FILA, BASE_FILA, TERCERA_FILA).
- Orden de llenado de formulario.
- Deteccion de carné cesado.
- Intentos de secuencia con numero de fila en tercera hoja.
- Resultado por secuencia (OK o NO ENCONTRADO).
- Escritura en tercera hoja y comparacion.

## Ejecucion

Instalacion:

```bash
pip install -r requirements.md
python -m playwright install chromium
```

Ejecucion en Windows:

```bat
run_carnet_emision.bat
```

Ejecucion directa:

```bash
python carnet_emision.py
```

## Requisitos de Google Cloud para escritura

Para que funcionen las actualizaciones en hojas:

1. Habilitar Google Sheets API en el proyecto de la cuenta de servicio.
2. Compartir las hojas con el client_email de la cuenta de servicio con rol Editor.
3. Configurar DRIVE_CREDENTIALS_JSON al archivo JSON correcto.

Si la API esta deshabilitada, el flujo principal puede continuar, pero fallaran las marcas en hojas (ejemplo: NO ENCONTRADO).
