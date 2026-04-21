import logging
import time
from typing import Callable

from playwright.sync_api import sync_playwright

from app import carnet_emision as core


AccionAutenticada = Callable[[object, logging.Logger, str], None]


def ejecutar_con_sesion_autenticada(
    grupo: str,
    logger_suffix: str,
    accion: AccionAutenticada,
    keep_browser_open_on_finish: bool = False,
) -> int:
    logger = core.setup_logger("carnet_emision", suffix=logger_suffix)
    logger.info("[SEGMENTADO] Iniciando flujo autenticado para grupo=%s", grupo)

    hold_browser_open = core._as_bool_env("HOLD_BROWSER_OPEN", default=False)
    headless = core._as_bool_env("CARNET_HEADLESS", default=False)
    keep_open_now = bool(
        (keep_browser_open_on_finish or hold_browser_open)
        and (not core._is_scheduled_mode())
        and (not headless)
    )

    playwright = sync_playwright().start()
    browser = None
    context = None

    try:
        browser, context, page = core._abrir_sesion_grupo(playwright, logger, grupo)
        core._ejecutar_login_en_pagina(page, logger, grupo)
        core._cerrar_paginas_extra_context(context, page, logger)

        accion(page, logger, grupo)

        if keep_open_now:
            logger.info("[%s] HOLD_BROWSER_OPEN=1. Esperando Ctrl+C", grupo)
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                logger.info("[%s] Interrupcion manual detectada", grupo)

        return 0
    except Exception as exc:
        logger.exception("[SEGMENTADO] Error en flujo %s: %s", logger_suffix, exc)
        return 1
    finally:
        try:
            if context is not None and not keep_open_now:
                context.close()
        except Exception:
            pass
        try:
            if browser is not None and not keep_open_now:
                browser.close()
        except Exception:
            pass
        try:
            playwright.stop()
        except Exception:
            pass
