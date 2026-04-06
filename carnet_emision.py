import logging
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
TEST_DIR = BASE_DIR / "test"
CACHE_DIR = BASE_DIR / "__pycache__"

URL_LOGIN = os.getenv(
    "CARNET_URL_LOGIN",
    "https://www.sucamec.gob.pe/sel/faces/login.xhtml?faces-redirect=true",
).strip()

CREDENCIALES = {
    "tipo_documento_valor": os.getenv("CARNET_TIPO_DOC", os.getenv("TIPO_DOC", "RUC")).strip(),
    "numero_documento": os.getenv("CARNET_NUMERO_DOCUMENTO", os.getenv("NUMERO_DOCUMENTO", "")).strip(),
    "usuario": os.getenv("CARNET_USUARIO_SEL", os.getenv("USUARIO_SEL", "")).strip(),
    "contrasena": os.getenv("CARNET_CLAVE_SEL", os.getenv("CLAVE_SEL", "")).strip(),
}

SEL = {
    "tab_tradicional": '#tabViewLogin a[href^="#tabViewLogin:j_idt"]:has-text("Autenticación Tradicional"), #tabViewLogin a:has-text("Autenticación Tradicional"), #tabViewLogin a:has-text("Autenticacion Tradicional")',
    "tipo_doc_select": "#tabViewLogin\\:tradicionalForm\\:tipoDoc_input",
    "numero_documento": "#tabViewLogin\\:tradicionalForm\\:documento",
    "usuario": "#tabViewLogin\\:tradicionalForm\\:usuario",
    "clave": "#tabViewLogin\\:tradicionalForm\\:clave",
    "captcha_input": "#tabViewLogin\\:tradicionalForm\\:textoCaptcha",
    "ingresar": "#tabViewLogin\\:tradicionalForm\\:ingresar",
}

SUCCESS_SELECTORS = [
    "#j_idt11\\:menuPrincipal",
    "#j_idt11\\:j_idt18",
    "form#gestionCitasForm",
]

ERROR_SELECTORS = [
    ".ui-messages-error",
    ".ui-message-error",
    ".ui-growl-message-error",
    ".mensajeError",
    "[class*='error']",
    "[class*='Error']",
]


def ensure_directories() -> None:
    for path in [LOGS_DIR, DATA_DIR, TEST_DIR, CACHE_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def setup_logger() -> logging.Logger:
    ensure_directories()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"carnet_emision_{stamp}.log"

    logger = logging.getLogger("carnet_emision")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    logger.info("Log inicializado en %s", log_file)
    return logger


def escribir_input_rapido(page, selector: str, valor: str) -> None:
    campo = page.locator(selector)
    campo.wait_for(state="visible", timeout=10000)
    campo.click()
    campo.fill(valor)
    campo.evaluate(
        'el => { el.dispatchEvent(new Event("input", {bubbles:true})); el.dispatchEvent(new Event("change", {bubbles:true})); }'
    )
    campo.blur()



def activar_pestana_autenticacion_tradicional(page) -> None:
    candidatos = [
        SEL["tab_tradicional"],
        '#tabViewLogin a:has-text("Autenticación Tradicional")',
        '#tabViewLogin a:has-text("Autenticacion Tradicional")',
    ]

    ultimo_error = None
    for selector in candidatos:
        try:
            tab = page.locator(selector)
            tab.first.wait_for(state="visible", timeout=3500)
            tab.first.click(timeout=3500)
            return
        except Exception as exc:
            ultimo_error = exc

    raise Exception(
        "No se pudo activar la pestaña de Autenticación Tradicional. "
        f"Detalle: {ultimo_error}"
    )



def validar_credenciales(logger: logging.Logger) -> None:
    faltantes = [
        key
        for key, value in CREDENCIALES.items()
        if key in {"numero_documento", "usuario", "contrasena"} and not value
    ]
    if faltantes:
        raise Exception(
            "Faltan credenciales en .env para este flujo: "
            f"{', '.join(faltantes)}"
        )
    logger.info("Credenciales validadas")



def esperar_resultado_login(page, timeout_ms: int = 8000) -> tuple[bool, str]:
    start = time.time()
    last_error = ""

    while (time.time() - start) * 1000 < timeout_ms:
        for selector in SUCCESS_SELECTORS:
            try:
                if page.locator(selector).first.is_visible(timeout=150):
                    return True, ""
            except Exception:
                pass

        for selector in ERROR_SELECTORS:
            try:
                loc = page.locator(selector)
                if loc.count() > 0:
                    text = (loc.first.inner_text() or "").strip()
                    if text:
                        last_error = text
                        return False, last_error
            except Exception:
                pass

        page.wait_for_timeout(150)

    return False, last_error or "No se confirmó sesión autenticada en el tiempo esperado"



def resolver_captcha_manual(logger: logging.Logger) -> None:
    run_mode = os.getenv("RUN_MODE", "manual").strip().lower()
    if run_mode == "scheduled":
        raise Exception("CAPTCHA_MANUAL_REQUERIDO_EN_SCHEDULED")

    logger.info("Modo manual para captcha activado")
    print("\n[MANUAL] Completa el captcha en el navegador y presiona ENTER aquí para continuar...")
    input()



def preparar_flujo_emision_carnet(logger: logging.Logger, page) -> None:
    logger.info("Login correcto. Aquí continúa el flujo nuevo de emisión de carnet.")
    logger.info("URL post-login: %s", page.url)



def ejecutar_flujo_login_carnet() -> None:
    logger = setup_logger()
    logger.info("INICIANDO FLUJO CARNET - Etapa de login")

    hold_browser_open = os.getenv("HOLD_BROWSER_OPEN", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "si",
        "sí",
    }
    headless = os.getenv("CARNET_HEADLESS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    validar_credenciales(logger)

    playwright = sync_playwright().start()
    browser = None
    context = None

    try:
        browser = playwright.chromium.launch(
            headless=headless,
            slow_mo=0,
            args=["--start-maximized", "--window-size=1920,1080", "--window-position=0,0"],
        )
        context = browser.new_context(no_viewport=True, ignore_https_errors=True)
        page = context.new_page()

        logger.info("Navegando a login: %s", URL_LOGIN)
        page.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=45000)

        activar_pestana_autenticacion_tradicional(page)
        page.locator(SEL["numero_documento"]).wait_for(state="visible", timeout=8000)

        page.select_option(SEL["tipo_doc_select"], value=CREDENCIALES["tipo_documento_valor"])
        page.wait_for_timeout(300)

        escribir_input_rapido(page, SEL["numero_documento"], CREDENCIALES["numero_documento"])
        escribir_input_rapido(page, SEL["usuario"], CREDENCIALES["usuario"])
        escribir_input_rapido(page, SEL["clave"], CREDENCIALES["contrasena"])
        logger.info("Credenciales cargadas en formulario")

        resolver_captcha_manual(logger)

        page.locator(SEL["captcha_input"]).wait_for(state="visible", timeout=10000)
        page.locator(SEL["ingresar"]).click(timeout=10000)
        logger.info("Login enviado, validando señales de UI")

        ok, error = esperar_resultado_login(page, timeout_ms=10000)
        if not ok:
            raise Exception(f"Login fallido: {error}")

        logger.info("Acceso exitoso")
        preparar_flujo_emision_carnet(logger, page)

        if hold_browser_open:
            logger.info("HOLD_BROWSER_OPEN=1. Navegador queda abierto hasta Ctrl+C")
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Interrupción manual detectada, cerrando navegador")

    except PlaywrightTimeoutError as exc:
        logger.exception("Timeout de Playwright: %s", exc)
        raise
    except Exception as exc:
        logger.exception("Error en flujo de login carnet: %s", exc)
        raise
    finally:
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        try:
            playwright.stop()
        except Exception:
            pass
        logger.info("Navegador cerrado")


if __name__ == "__main__":
    ejecutar_flujo_login_carnet()
