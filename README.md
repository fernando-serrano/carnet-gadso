# Flujo Emisión de Carnet SUCAMEC

Este workspace incluye un flujo base para emisión de carnet que replica la lógica automática de login del flujo original, incluyendo OCR de captcha y orquestación opcional con workers en modo scheduled.

## Estructura creada

- `carnet_emision.py`: script del flujo de carnet con login automático + OCR + workers
- `run_carnet_emision.bat`: ejecuta el flujo en Windows
- `logs/`: salida de logs por ejecución
- `data/`: insumos de datos para el flujo
- `test/`: espacio para pruebas
- `__pycache__/`: caché de Python
- `.gitignore`: exclusiones para cachés, logs, entornos y `.env`

## Variables de entorno

El script usa primero variables específicas `CARNET_*` y si no existen hace fallback a las actuales:

- `CARNET_TIPO_DOC` (fallback `TIPO_DOC`)
- `CARNET_NUMERO_DOCUMENTO` (fallback `NUMERO_DOCUMENTO`)
- `CARNET_USUARIO_SEL` (fallback `USUARIO_SEL`)
- `CARNET_CLAVE_SEL` (fallback `CLAVE_SEL`)
- `CARNET_URL_LOGIN` (default URL login SEL)
- `CARNET_HEADLESS` (`0` o `1`)
- `CARNET_OCR_MAX_INTENTOS` (default `6`)
- `HOLD_BROWSER_OPEN` (`0` o `1`)
- `RUN_MODE` (`manual` o `scheduled`)
- `CARNET_GRUPOS` (default `SELVA,JV`)
- `MAX_LOGIN_RETRIES_PER_GROUP` (default `12`)
- `LOGIN_VALIDATION_TIMEOUT_MS` (default `6000`)

Variables de workers (modo scheduled):

- `SCHEDULED_MULTIWORKER` (`1` activa orquestador)
- `SCHEDULED_WORKERS` (cantidad de workers, default `2`, máximo `4`)

## Ejecución

En Windows:

```bat
run_carnet_emision.bat
```

O directo con Python:

```bash
python carnet_emision.py
```

## Estado actual del flujo

Actualmente el flujo implementa:

1. Inicialización de carpetas y logger.
2. Apertura de Playwright + Chromium.
3. Navegación a login SUCAMEC.
4. Activación de pestaña de autenticación tradicional.
5. Carga de credenciales.
6. Resolución automática de captcha con OCR (easyocr).
7. Validación de login por señales de UI.
8. Reintentos de login por grupo.
9. Orquestación de workers en modo scheduled (subprocesos aislados).
10. Guardado de logs en archivo tanto en ejecución directa como desde `.bat`.

Después del login exitoso, queda marcado el punto para implementar la lógica específica de emisión de carnet.
