# Flujo Emisión de Carnet SUCAMEC

Este workspace ahora incluye un flujo base para **emisión de carnet** que reutiliza la lógica del login del flujo original y deja un punto de extensión para implementar los pasos posteriores.

## Estructura creada

- `carnet_emision.py`: script base del nuevo flujo (hasta login)
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
- `HOLD_BROWSER_OPEN` (`0` o `1`)
- `RUN_MODE` (`manual` o `scheduled`)

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
6. Resolución manual de captcha.
7. Validación de login por señales de UI.

Después del login exitoso, queda marcado el punto para implementar la lógica específica de emisión de carnet.
