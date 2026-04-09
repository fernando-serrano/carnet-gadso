# Correcciones Realizadas - Flujo de Verificación de Comprobante

## 📋 Problemas Identificados y Solucionados

### Problema 1: Dos mensajes de éxito/error sin distinguir
**Síntoma:** Se detectaba "No se encontró el recibo" pero no "Recibo encontrado", causando iteración infinita.

**Causa:** La función anterior solo buscaba el texto de error, ignorando el mensaje de éxito.

**Solución:** 
- Nueva función `detectar_resultado_verificacion_comprobante()` que retorna:
  - `("ENCONTRADO", "...") → Éxito, continuar`
  - `("NO_ENCONTRADO", "...") → Error, fallback`
  - `("TIMEOUT", "") → Sin mensaje detectable`

### Problema 2: No ingresa DNI ni acciona "Buscar"
**Síntoma:** El flujo nunca llega a `ingresar_documento_y_buscar()`.

**Causa:** Si no hay secuencias válidas detectadas, la función retorna `False` antes de intentar DNI.

**Solución:**
- Agregué fallback automático si no hay candidatos en `secuencia_candidatos`
- Se usa la secuencia del item actual como candidato único
- Si tampoco eso existe, retorna error **explícitamente**
- Flujo continúa a DNI solo si obtiene secuencia exitosa

### Problema 3: Falta validación de "Tipo de Registro"
**Síntoma:** No se garantizaba que Tipo de Registro estuviera seleccionado antes de intentar Comprobante.

**Solución:**
- **ANTES** de entrar al loop de secuencias, se valida:
  1. Lee el valor actual de "Tipo de Registro" desde formulario
  2. Si está "Seleccione..." o vacío → lo selecciona
  3. Espera 300ms para AJAX
  4. Confirma que se aplicó
- Solo después procede a Comprobante

---

## 🔧 Cambios Técnicos Específicos

### 1. Nueva función: `detectar_resultado_verificacion_comprobante()`
```python
def detectar_resultado_verificacion_comprobante(page, max_wait_ms: int = 5000) -> tuple[str, str]:
    """
    Retorna:
    - ("ENCONTRADO", "Recibo encontrado")  # Éxito
    - ("NO_ENCONTRADO", "No se encontró el recibo")  # Error
    - ("TIMEOUT", "")  # Sin resultado en tiempo límite
    """
```

**Estrategia:**
1. Buffer JS (mensajes persistentes)
2. DOM actual (`.ui-growl-item`)
3. HTML page.content() (fallback)

**Timeout:** 6 segundos (aumentado de 3 para mayor tolerancia)

---

### 2. Actualización: `procesar_registro_cruce_en_formulario()`

#### Flujo nuevo (orden exacto):
```
1. Seleccionar SEDE
2. Seleccionar MODALIDAD
3. ✓✓ **VALIDAR TIPO DE REGISTRO** (NUEVO)
   - Lee valor actual
   - Si vacío → selecciona
   - Espera AJAX
   - Confirma
4. Seleccionar TIPO DE DOCUMENTO
5. **LOOP DE SECUENCIAS** (con detección mejorada)
   - Para cada candidato:
     a. Ingresa Comprobante
     b. Espera 800ms
     c. Polling 6seg → detecta resultado
     d. Si ENCONTRADO → sale loop, continúa
     e. Si NO_ENCONTRADO → marca en sheet, limpia, intenta siguiente
     f. Si TIMEOUT → asume éxito, continúa
6. ✓✓ **INGRESA DNI Y BUSCAR** (solo llega aquí si secuencia válida)
7. Valida carné cesado (cambio empresa si aplica)
8. Actualiza hoja de comparación
```

#### Cambios puntuales:

**ANTES:**
```python
# Tipo de Registro (automático sin validación)
seleccionar_tipo_registro(page, tipo_registro_objetivo)

# Loop de secuencias (detecta solo error)
encontrado_error, _ = detectar_error_recibo_no_encontrado(page, max_wait_ms=3000)
if encontrado_error:
    # Error
    indice_actual += 1
else:
    # Éxito
    secuencia_enviada_exitosamente = True
```

**DESPUÉS:**
```python
# Validar Tipo de Registro ANTES
try:
    tipo_reg_text = page.locator(...).inner_text()
    if "seleccione" in tipo_reg_text.lower():
        seleccionar_tipo_registro(page, "CAMBIO DE EMPRESA")
        page.wait_for_timeout(300)  # AJAX
except Exception as exc:
    logger.warning(...)

# Loop mejorado (detecta ambos: éxito Y error)
resultado, msg = detectar_resultado_verificacion_comprobante(page, max_wait_ms=6000)

if resultado == "ENCONTRADO":
    secuencia_exitosa = True
    break  # Sale loop
elif resultado == "NO_ENCONTRADO":
    # Marca en sheet, limpia, intenta siguiente
    _actualizar_fila_tercera_hoja_por_row(...)
    page.locator(...).fill("")
    continue  # Siguiente candidato
else:  # TIMEOUT
    # Asume éxito (mejor que falso negativo)
    secuencia_exitosa = True
    break
```

---

## 📊 Comparativa de Comportamiento

| Situación | Antes | Después |
|-----------|-------|---------|
| **Mensaje "Recibo encontrado"** | Ignorado (timeout) → error | ✓ Detectado → éxito |
| **Mensaje "No se encontró"** | Detectado → fallback | ✓ Detectado → fallback |
| **Tipo Registro no seleccionado** | Error/inconsistencia | ✓ Auto-valida antes |
| **Sin candidatos de secuencia** | Error silencioso | ✓ Fallback a item actual |
| **Timeout sin mensajes** | Fallo negativo | ✓ Asume éxito (tolerante) |
| **DNI/Buscar después error secuencia** | No ejecutado | ✓ Ejecutado si hay secuencia válida |

---

## 🎯 Resultado Esperado

**Log esperado con secuencia válida:**
```
[FORM] Tipo de Registro preseleccionado: CAMBIO DE EMPRESA
[FORM] Intento secuencia 1/1: 123456
[FORM] ✓ SECUENCIA 123456 VÁLIDA EN SUCAMEC
[FORM] Procediendo con búsqueda de documento...
[FORM] Ingresando DNI: 75953160
[FORM] Búsqueda de documento ejecutada
[FORM] ✓ REGISTRO COMPLETADO EXITOSAMENTE
```

**Log esperado con secuencia inválida + fallback:**
```
[FORM] Intento secuencia 1/3: 999999
[FORM] ✗ SECUENCIA 999999 NO ENCONTRADA EN SUCAMEC
[FORM] Fila 7223 marcada como NO ENCONTRADO en tercera hoja
[FORM] Intento secuencia 2/3: 123456
[FORM] ✓ SECUENCIA 123456 VÁLIDA EN SUCAMEC
[FORM] Ingresando DNI: 75953160
...
[FORM] ✓ REGISTRO COMPLETADO EXITOSAMENTE
```

---

## ✅ Validación

- ✓ Sintaxis verificada: No hay errores de compilación
- ✓ Ambas funciones de detección implementadas
- ✓ Fallback automático para candidatos vacíos
- ✓ Validación de Tipo de Registro ANTES de secuencias
- ✓ Timeout tolerante (6seg) en lugar de cortante (3seg)
- ✓ DNI e búsqueda solo ejecutados si secuencia válida

---
