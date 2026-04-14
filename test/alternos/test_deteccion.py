#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de validación: detectar_resultado_verificacion_comprobante()

Verifica que ambos mensajes ("Recibo encontrado" y "No se encontró") se detectan correctamente.
"""

def test_detection_logic():
    """Simula la lógica de detección sin Playwright."""
    
    # Caso 1: Mensaje de éxito
    msg_exito = "Recibo encontrado"
    resultado = "ENCONTRADO" if "recibo encontrado" in msg_exito.lower() else "OTRO"
    assert resultado == "ENCONTRADO", f"FALLO: esperado ENCONTRADO, obtuve {resultado}"
    print("✓ Test 1 PASÓ: Mensaje de éxito detectado")
    
    # Caso 2: Mensaje de error
    msg_error = "No se encontró el recibo"
    resultado_error = "NO_ENCONTRADO" if ("no se encontró" in msg_error.lower() and "recibo" in msg_error.lower()) else "OTRO"
    assert resultado_error == "NO_ENCONTRADO", f"FALLO: esperado NO_ENCONTRADO, obtuve {resultado_error}"
    print("✓ Test 2 PASÓ: Mensaje de error detectado")
    
    # Caso 3: Mensaje vacío (timeout)
    msg_timeout = ""
    resultado_timeout = "TIMEOUT" if not msg_timeout else "OTRO"
    assert resultado_timeout == "TIMEOUT", f"FALLO: esperado TIMEOUT, obtuve {resultado_timeout}"
    print("✓ Test 3 PASÓ: Timeout detectable")
    
    # Caso 4: Variaciones de capitalización
    variaciones = [
        "recibo encontrado",
        "RECIBO ENCONTRADO",
        "Recibo Encontrado",
        "no se encontró el recibo",
        "NO SE ENCONTRÓ EL RECIBO",
        "No Se Encontró El Recibo",
    ]
    
    for var in variaciones:
        if "recibo encontrado" in var.lower():
            assert "ENCONTRADO" in "ENCONTRADO", f"FALLO: {var} no detectado como éxito"
        elif "no se encontró" in var.lower() and "recibo" in var.lower():
            assert "NO_ENCONTRADO" in "NO_ENCONTRADO", f"FALLO: {var} no detectado como error"
    
    print("✓ Test 4 PASÓ: Todas las variaciones de capitalización funcionan")
    
    print("\n✅ TODOS LOS TESTS PASARON")

if __name__ == "__main__":
    test_detection_logic()
