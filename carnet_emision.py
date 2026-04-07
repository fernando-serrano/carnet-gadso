import os
import queue
import re
import subprocess
import sys
import time
import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import logging
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

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

DEFAULT_GSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/1I5CmLAxZxA5gIlHz_m5kDPTaHIs1yOEWvy7tN4Ia2hs/"
    "edit?pli=1&gid=999619533#gid=999619533"
)

CREDENCIALES_JV = {
    "tipo_documento_valor": os.getenv("CARNET_TIPO_DOC", os.getenv("TIPO_DOC", "RUC")).strip(),
    "numero_documento": os.getenv("CARNET_NUMERO_DOCUMENTO", os.getenv("NUMERO_DOCUMENTO", "")).strip(),
    "usuario": os.getenv("CARNET_USUARIO_SEL", os.getenv("USUARIO_SEL", "")).strip(),
    "contrasena": os.getenv("CARNET_CLAVE_SEL", os.getenv("CLAVE_SEL", "")).strip(),
}

CREDENCIALES_SELVA = {
    "tipo_documento_valor": os.getenv("CARNET_SELVA_TIPO_DOC", os.getenv("SELVA_TIPO_DOC", "RUC")).strip(),
    "numero_documento": os.getenv("CARNET_SELVA_NUMERO_DOCUMENTO", os.getenv("SELVA_NUMERO_DOCUMENTO", "")).strip(),
    "usuario": os.getenv("CARNET_SELVA_USUARIO_SEL", os.getenv("SELVA_USUARIO_SEL", "")).strip(),
    "contrasena": os.getenv("CARNET_SELVA_CLAVE_SEL", os.getenv("SELVA_CLAVE_SEL", "")).strip(),
}

SEL = {
    "tab_tradicional": '#tabViewLogin a[href^="#tabViewLogin:j_idt"]:has-text("Autenticación Tradicional"), #tabViewLogin a:has-text("Autenticación Tradicional"), #tabViewLogin a:has-text("Autenticacion Tradicional")',
    "tipo_doc_select": "#tabViewLogin\\:tradicionalForm\\:tipoDoc_input",
    "numero_documento": "#tabViewLogin\\:tradicionalForm\\:documento",
    "usuario": "#tabViewLogin\\:tradicionalForm\\:usuario",
    "clave": "#tabViewLogin\\:tradicionalForm\\:clave",
    "captcha_img": "#tabViewLogin\\:tradicionalForm\\:imgCaptcha",
    "captcha_input": "#tabViewLogin\\:tradicionalForm\\:textoCaptcha",
    "boton_refresh": "#tabViewLogin\\:tradicionalForm\\:botonCaptcha",
    "ingresar": "#tabViewLogin\\:tradicionalForm\\:ingresar",
    "menu_root": "#j_idt11\\:menuPrincipal, #j_idt11\\:menuprincipal",
    "menu_header_dssp": '.ui-panelmenu-header:has(a:text-is("DSSP")), .ui-panelmenu-header:has(a:has-text("DSSP"))',
    "menu_item_carne": '.ui-menuitem-link:has(span.ui-menuitem-text:text-is("CARNÉ")), .ui-menuitem-link:has(span.ui-menuitem-text:text-is("CARNE")), .ui-menuitem-link:has(span.ui-menuitem-text:has-text("CARN"))',
    "menu_item_crear_solicitud": '.ui-menuitem-link:has(span.ui-menuitem-text:text-is("CREAR SOLICITUD")), .ui-menuitem-link:has(span.ui-menuitem-text:has-text("CREAR SOLICITUD"))',
    "menu_item_crear_solicitud_onclick": 'a[onclick*="addSubmitParam"][onclick*="j_idt11:menuprincipal"]:has(span.ui-menuitem-text:text-is("CREAR SOLICITUD")), a[onclick*="addSubmitParam"][onclick*="j_idt11:menuPrincipal"]:has(span.ui-menuitem-text:text-is("CREAR SOLICITUD"))',
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


OCR_AVAILABLE = False
EASYOCR_READER = None
EASYOCR_ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
np = None

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    from io import BytesIO
    import numpy as np
    import easyocr

    easyocr_use_gpu = str(os.getenv("EASYOCR_USE_GPU", "0") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "si",
        "sí",
    }
    langs_env = str(os.getenv("EASYOCR_LANGS", "en") or "en")
    langs = [x.strip() for x in langs_env.split(",") if x.strip()] or ["en"]
    EASYOCR_ALLOWLIST = str(
        os.getenv("EASYOCR_ALLOWLIST", EASYOCR_ALLOWLIST) or EASYOCR_ALLOWLIST
    ).strip() or EASYOCR_ALLOWLIST
    EASYOCR_READER = easyocr.Reader(langs, gpu=easyocr_use_gpu, verbose=False)
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False


def ensure_directories() -> None:
    for path in [LOGS_DIR, DATA_DIR, TEST_DIR, CACHE_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def setup_logger(name: str = "carnet_emision", suffix: str = "") -> logging.Logger:
    ensure_directories()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix_clean = f"_{suffix}" if suffix else ""
    log_file = LOGS_DIR / f"{name}{suffix_clean}_{stamp}.log"

    logger = logging.getLogger(f"{name}{suffix_clean}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    logger.info("Log inicializado en %s", log_file)
    return logger


def _as_bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "si", "sí", "on"}


def _safe_int_env(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default)) or str(default)).strip())
    except Exception:
        return default


def _detect_windows_screen_size(default_w: int = 1920, default_h: int = 1080):
    """Retorna resolución efectiva (espacio lógico) en Windows."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        w = int(user32.GetSystemMetrics(0))
        h = int(user32.GetSystemMetrics(1))
        if w >= 800 and h >= 600:
            return w, h
    except Exception:
        pass
    return default_w, default_h


def _build_launch_args_for_window() -> list:
    tile_enabled = _as_bool_env("BROWSER_TILE_ENABLE", default=False)
    if not tile_enabled:
        return ["--disable-infobars", "--start-maximized", "--window-size=1920,1080", "--window-position=0,0"]

    tile_total = max(1, _safe_int_env("BROWSER_TILE_TOTAL", 1))
    tile_index = _safe_int_env("BROWSER_TILE_INDEX", 0)
    if tile_index < 0:
        tile_index = 0
    if tile_index >= tile_total:
        tile_index = tile_total - 1

    tile_screen_w = _safe_int_env("BROWSER_TILE_SCREEN_W", 1920)
    tile_screen_h = _safe_int_env("BROWSER_TILE_SCREEN_H", 1080)
    tile_top_offset = max(0, _safe_int_env("BROWSER_TILE_TOP_OFFSET", 0))
    tile_gap = max(0, _safe_int_env("BROWSER_TILE_GAP", 6))
    tile_frame_pad = max(0, _safe_int_env("BROWSER_TILE_FRAME_PAD", 2))

    cols = 2 if tile_total == 2 else (1 if tile_total == 1 else 2)
    rows = (tile_total + cols - 1) // cols
    usable_h = max(480, tile_screen_h - tile_top_offset)
    cell_w = max(360, tile_screen_w // cols)
    cell_h = max(320, usable_h // rows)

    tile_w = max(320, cell_w - (tile_gap * 2) - tile_frame_pad)
    tile_h = max(260, cell_h - (tile_gap * 2))
    col = tile_index % cols
    row = tile_index // cols
    tile_x = col * cell_w + tile_gap + (tile_frame_pad if col > 0 else 0)
    tile_y = tile_top_offset + row * cell_h + tile_gap

    return [
        "--disable-infobars",
        f"--window-size={tile_w},{tile_h}",
        f"--window-position={tile_x},{tile_y}",
    ]


def _is_scheduled_mode() -> bool:
    return os.getenv("RUN_MODE", "manual").strip().lower() == "scheduled"


def _multiworker_habilitado() -> bool:
    if not _is_scheduled_mode():
        return False
    if _as_bool_env("MULTIWORKER_CHILD", default=False):
        return False
    return _as_bool_env("SCHEDULED_MULTIWORKER", default=True)


def escribir_input_rapido(page, selector: str, valor: str) -> None:
    campo = page.locator(selector)
    campo.wait_for(state="visible", timeout=12000)
    campo.click()
    campo.fill(valor)
    campo.evaluate(
        'el => { el.dispatchEvent(new Event("input", {bubbles:true})); el.dispatchEvent(new Event("change", {bubbles:true})); }'
    )
    campo.blur()
    if (campo.input_value() or "") != valor:
        campo.click()
        campo.press("Control+A")
        campo.press("Backspace")
        campo.type(valor, delay=12)
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


def validar_resultado_login_por_ui(page, timeout_ms: int = 12000):
    inicio = time.time()
    while (time.time() - inicio) * 1000 < timeout_ms:
        try:
            url_actual = (page.url or "").lower()
            if "/faces/aplicacion/inicio.xhtml" in url_actual:
                return True, None, time.time() - inicio
        except Exception:
            pass

        for sel in SUCCESS_SELECTORS:
            try:
                if page.locator(sel).first.is_visible(timeout=120):
                    return True, None, time.time() - inicio
            except Exception:
                pass

        for sel in ERROR_SELECTORS:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    txt = (loc.first.inner_text() or "").strip()
                    if txt:
                        return False, txt, time.time() - inicio
            except Exception:
                pass
        page.wait_for_timeout(140)

    return False, "No se confirmó sesión autenticada en el tiempo esperado", time.time() - inicio


def pagina_muestra_servicio_no_disponible(page) -> bool:
    selectores_ok = [
        SEL["tab_tradicional"],
        SEL["numero_documento"],
        "#j_idt11\\:menuPrincipal",
        "form#gestionCitasForm",
    ]
    for sel in selectores_ok:
        try:
            if page.locator(sel).first.is_visible(timeout=150):
                return False
        except Exception:
            pass

    try:
        t = (page.title() or "").lower()
        if "service unavailable" in t:
            return True
    except Exception:
        pass

    try:
        h1 = (page.locator("h1").first.inner_text() or "").strip().lower()
        if "service unavailable" in h1:
            return True
    except Exception:
        pass

    try:
        body = (page.locator("body").inner_text(timeout=350) or "").lower()
        if "service unavailable" in body and "sucamec" in body:
            return True
    except Exception:
        pass

    return False


def esperar_hasta_servicio_disponible(page, url_objetivo: str, espera_segundos: int = 8):
    intento = 0
    while pagina_muestra_servicio_no_disponible(page):
        intento += 1
        page.wait_for_timeout(max(1, int(espera_segundos)) * 1000)
        page.goto(url_objetivo, wait_until="domcontentloaded", timeout=45000)


def corregir_captcha_ocr(texto_raw: str) -> str:
    if not texto_raw:
        return ""
    texto = str(texto_raw).strip().upper().replace(" ", "").replace("\n", "").replace("\r", "")
    texto = "".join(c for c in texto if c.isalnum())
    return texto


def validar_captcha_texto(texto: str) -> bool:
    return bool(texto) and len(texto) == 5 and texto.isalnum()


def preprocesar_imagen_captcha(img_bytes: bytes, variante: int = 0):
    img = Image.open(BytesIO(img_bytes)).convert("L")
    if variante == 0:
        img = ImageEnhance.Contrast(img).enhance(3.5)
        w, h = img.size
        img = img.resize((w * 3, h * 3), Image.LANCZOS)
        img = img.filter(ImageFilter.MedianFilter(size=3))
        img = ImageOps.invert(img)
        img = img.point(lambda p: 255 if p > 130 else 0)
    elif variante == 1:
        img = ImageEnhance.Contrast(img).enhance(2.8)
        w, h = img.size
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
        img = img.filter(ImageFilter.MedianFilter(size=5))
        img = img.point(lambda p: 255 if p > 160 else 0)
    else:
        img = ImageEnhance.Contrast(img).enhance(4.0)
        w, h = img.size
        img = img.resize((w * 3, h * 3), Image.LANCZOS)
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
        img = ImageOps.invert(img)
        img = img.point(lambda p: 255 if p > 110 else 0)
    return img


def _leer_texto_easyocr_desde_imagen(img, decoder: str = "greedy") -> str:
    if EASYOCR_READER is None or np is None:
        return ""

    try:
        arr = np.array(img)
    except Exception:
        return ""

    try:
        resultados = EASYOCR_READER.readtext(
            arr,
            detail=0,
            paragraph=False,
            allowlist=EASYOCR_ALLOWLIST,
            decoder=decoder,
        )
    except TypeError:
        resultados = EASYOCR_READER.readtext(
            arr,
            detail=0,
            paragraph=False,
            allowlist=EASYOCR_ALLOWLIST,
        )
    except Exception:
        return ""

    if isinstance(resultados, (list, tuple)):
        return " ".join(str(x or "") for x in resultados).strip()
    return str(resultados or "").strip()


def solve_captcha_ocr_base(page, captcha_img_selector: str, boton_refresh_selector: str, logger: logging.Logger, max_intentos: int = 6) -> str:
    if not OCR_AVAILABLE:
        raise Exception("OCR no disponible. Instala easyocr, pillow y numpy para modo automático.")

    # Fast path por defecto: menos combinaciones para bajar latencia por intento.
    usar_beamsearch = _as_bool_env("CARNET_OCR_USE_BEAMSEARCH", default=False)
    decoders_fast = ["greedy"]
    decoders_full = ["greedy", "beamsearch"] if usar_beamsearch else ["greedy"]
    variantes_fast = [0]
    variantes_full = [0, 1, 2]

    for intento in range(1, max(1, max_intentos) + 1):
        t0 = time.time()
        img_locator = page.locator(captcha_img_selector)
        img_locator.wait_for(state="visible", timeout=12000)
        img_bytes = img_locator.screenshot()

        def _buscar_candidato(variantes, decoders):
            for variante in variantes:
                img_proc = preprocesar_imagen_captcha(img_bytes, variante=variante)
                for decoder in decoders:
                    lectura = corregir_captcha_ocr(_leer_texto_easyocr_desde_imagen(img_proc, decoder=decoder))
                    if validar_captcha_texto(lectura):
                        return lectura
            return ""

        # Etapa rápida: 1 variante + decoder greedy.
        candidato = _buscar_candidato(variantes_fast, decoders_fast)

        # Fallback solo si no se pudo resolver en etapa rápida.
        if not candidato:
            candidato = _buscar_candidato(variantes_full, decoders_full)

        if candidato:
            logger.info(
                "Captcha OCR resuelto en intento %s: %s (%.2fs)",
                intento,
                candidato,
                time.time() - t0,
            )
            return candidato

        logger.warning(
            "OCR no encontró captcha válido en intento %s/%s (%.2fs)",
            intento,
            max_intentos,
            time.time() - t0,
        )
        if boton_refresh_selector:
            try:
                page.locator(boton_refresh_selector).click(timeout=4000)
                page.wait_for_timeout(120)
            except Exception:
                pass

    raise Exception(f"No se pudo resolver captcha automáticamente tras {max_intentos} intentos")


def solve_captcha_ocr(page, logger: logging.Logger) -> str:
    return solve_captcha_ocr_base(
        page,
        captcha_img_selector=SEL["captcha_img"],
        boton_refresh_selector=SEL["boton_refresh"],
        logger=logger,
        max_intentos=_safe_int_env("CARNET_OCR_MAX_INTENTOS", 4),
    )


def validar_credenciales_configuradas(credenciales: dict, etiqueta: str):
    faltantes = []
    if not str(credenciales.get("numero_documento", "")).strip():
        faltantes.append("numero_documento")
    if not str(credenciales.get("usuario", "")).strip():
        faltantes.append("usuario")
    if not str(credenciales.get("contrasena", "")).strip():
        faltantes.append("contrasena")
    if faltantes:
        raise Exception(
            f"Faltan credenciales para grupo {etiqueta}: {faltantes}. Configúralas en .env"
        )


def _normalizar_columna(nombre: str) -> str:
    return str(nombre or "").strip().lower()


def _build_google_sheet_csv_url(sheet_url: str) -> str:
    raw = str(sheet_url or "").strip()
    if not raw:
        raise Exception("URL de Google Sheets vacía")

    parsed = urlparse(raw)
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", parsed.path or "")
    if not m:
        raise Exception("No se pudo extraer el ID del Google Sheet desde la URL")
    sheet_id = m.group(1)

    gid = None
    q = parse_qs(parsed.query or "")
    if q.get("gid"):
        gid = q.get("gid")[0]
    if not gid and parsed.fragment:
        frag = parse_qs(parsed.fragment)
        if frag.get("gid"):
            gid = frag.get("gid")[0]
        elif "gid=" in parsed.fragment:
            gid = parsed.fragment.split("gid=", 1)[1].split("&", 1)[0]
    gid = str(gid or "0").strip() or "0"

    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def imprimir_muestra_google_sheet(logger: logging.Logger, max_rows: int = 5) -> None:
    """Lee una hoja de Google Sheets vía CSV y muestra una muestra de registros."""
    gsheet_url = str(os.getenv("CARNET_GSHEET_URL", DEFAULT_GSHEET_URL) or DEFAULT_GSHEET_URL).strip()
    csv_url = _build_google_sheet_csv_url(gsheet_url)

    req = Request(
        csv_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; carnet-emision-bot/1.0)"},
    )
    with urlopen(req, timeout=25) as resp:
        content = resp.read()

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        logger.warning("Google Sheet accesible, pero no devolvió filas")
        return

    col_dni = None
    col_departamento = None
    col_puesto = None
    for col in (reader.fieldnames or []):
        ncol = _normalizar_columna(col)
        if col_dni is None and ncol == "dni":
            col_dni = col
        if col_departamento is None and "indicar el departamento donde labora" in ncol:
            col_departamento = col
        if col_puesto is None and ncol == "puesto":
            col_puesto = col

    faltantes = []
    if not col_dni:
        faltantes.append("DNI")
    if not col_departamento:
        faltantes.append("Indicar el departamento donde Labora o donde postuló")
    if not col_puesto:
        faltantes.append("PUESTO")
    if faltantes:
        raise Exception(f"No se encontraron columnas esperadas en Google Sheet: {faltantes}")

    total = len(rows)
    limite = max(1, int(max_rows or 5))
    logger.info("Google Sheet accesible: %s", csv_url)
    logger.info("Filas totales detectadas: %s", total)
    logger.info("Mostrando %s registros de muestra", min(limite, total))

    mostrados = 0
    for row in rows:
        dni = str(row.get(col_dni, "") or "").strip()
        dep = str(row.get(col_departamento, "") or "").strip()
        puesto = str(row.get(col_puesto, "") or "").strip()
        if not dni and not dep and not puesto:
            continue
        mostrados += 1
        logger.info("Muestra %s | DNI=%s | Departamento=%s | Puesto=%s", mostrados, dni, dep, puesto)
        if mostrados >= limite:
            break

    if mostrados == 0:
        logger.warning("No se encontraron filas con datos en las columnas clave")


def esperar_ajax_primefaces(page, timeout_ms: int = 7000) -> None:
    """Espera a que la cola AJAX de PrimeFaces quede vacía (si existe)."""
    try:
        page.wait_for_function(
            """() => {
                try {
                    if (!window.PrimeFaces || !PrimeFaces.ajax || !PrimeFaces.ajax.Queue) return true;
                    const q = PrimeFaces.ajax.Queue;
                    if (typeof q.isEmpty === 'function') return q.isEmpty();
                    const arr = q.requests || q.queue || [];
                    return !arr || arr.length === 0;
                } catch (e) {
                    return true;
                }
            }""",
            timeout=max(1000, int(timeout_ms)),
        )
    except Exception:
        pass


def validar_vista_crear_solicitud_por_ui(page, timeout_ms: int = 3000) -> bool:
    """
    Confirma vista de CREAR SOLICITUD por UI (sin depender de URL).
    Soporta selector personalizado opcional vía CARNET_CREAR_SOLICITUD_SELECTOR.
    """
    custom_selector = str(os.getenv("CARNET_CREAR_SOLICITUD_SELECTOR", "") or "").strip()
    deadline = time.time() + (max(600, int(timeout_ms)) / 1000.0)

    while time.time() < deadline:
        if custom_selector:
            try:
                if page.locator(custom_selector).first.is_visible(timeout=150):
                    return True
            except Exception:
                pass

        try:
            ok = page.evaluate(
                """() => {
                    const candidates = [
                        '.ui-layout-center',
                        '#j_idt11\\:content',
                        '#contenido',
                        '#principal',
                        '#main',
                    ];
                    let root = null;
                    for (const sel of candidates) {
                        const el = document.querySelector(sel);
                        if (el && el.offsetParent !== null) {
                            root = el;
                            break;
                        }
                    }
                    if (!root) return false;
                    const txt = String(root.innerText || '').replace(/\\s+/g, ' ').toUpperCase();
                    return txt.includes('CREAR SOLICITUD');
                }"""
            )
            if bool(ok):
                return True
        except Exception:
            pass

        page.wait_for_timeout(150)

    return False


def navegar_dssp_carne_crear_solicitud(page, logger: logging.Logger) -> None:
    """Navega en el panel lateral por DSSP -> CARNÉ -> CREAR SOLICITUD."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass

    # Fast-path: click directo al link JSF de CREAR SOLICITUD por onclick.
    try:
        page.locator(SEL["menu_root"]).first.wait_for(state="visible", timeout=5000)
        click_directo = page.evaluate(
            """() => {
                const anchors = Array.from(document.querySelectorAll('a[onclick*="addSubmitParam"][onclick*="menuprincipal"], a[onclick*="addSubmitParam"][onclick*="menuPrincipal"]'));
                const target = anchors.find((a) => ((a.textContent || '').replace(/\\s+/g, ' ').trim().toUpperCase() === 'CREAR SOLICITUD'));
                if (!target) return false;
                target.click();
                return true;
            }"""
        )
        if click_directo:
            logger.info("Fast-path: click directo en CREAR SOLICITUD (onclick JSF)")
            try:
                page.wait_for_load_state("networkidle", timeout=7000)
            except Exception:
                pass
            esperar_ajax_primefaces(page, timeout_ms=5000)
            if validar_vista_crear_solicitud_por_ui(page, timeout_ms=2200):
                logger.info("Vista CREAR SOLICITUD confirmada por UI")
            else:
                logger.warning("No se pudo confirmar la vista CREAR SOLICITUD por UI, pero el click JSF fue ejecutado")
            return
    except Exception:
        pass

    root = page.locator(SEL["menu_root"]).first
    root.wait_for(state="visible", timeout=12000)

    header_dssp = root.locator(SEL["menu_header_dssp"]).first
    header_dssp.wait_for(state="visible", timeout=8000)

    aria_expanded = (header_dssp.get_attribute("aria-expanded") or "").strip().lower()
    if aria_expanded != "true":
        header_dssp.click(timeout=8000)
        page.wait_for_timeout(250)
        aria_expanded = (header_dssp.get_attribute("aria-expanded") or "").strip().lower()
        if aria_expanded != "true":
            raise Exception("No se pudo expandir el menú DSSP")
    logger.info("Menú DSSP expandido")

    item_carne = root.locator(SEL["menu_item_carne"]).first
    item_carne.wait_for(state="visible", timeout=8000)
    item_carne.click(timeout=8000)
    logger.info("Click en opción CARNÉ")

    item_crear = root.locator(SEL["menu_item_crear_solicitud_onclick"]).first
    try:
        item_crear.wait_for(state="visible", timeout=4500)
    except Exception:
        # Si CARNÉ colapsa/expande en dos fases, repetimos el click una vez.
        item_carne.click(timeout=8000)
        try:
            item_crear.wait_for(state="visible", timeout=3500)
        except Exception:
            item_crear = root.locator(SEL["menu_item_crear_solicitud"]).first
            item_crear.wait_for(state="visible", timeout=6000)

    item_crear.click(timeout=10000)

    # Fallback fuerte: click por JS en caso de overlays/transiciones de PrimeFaces.
    try:
        page.evaluate(
            """() => {
                const anchors = Array.from(document.querySelectorAll('a[onclick*="addSubmitParam"][onclick*="menuprincipal"], a[onclick*="addSubmitParam"][onclick*="menuPrincipal"]'));
                const target = anchors.find((a) => ((a.textContent || '').replace(/\\s+/g, ' ').trim().toUpperCase() === 'CREAR SOLICITUD'));
                if (target) target.click();
            }"""
        )
    except Exception:
        pass

    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass
    esperar_ajax_primefaces(page, timeout_ms=6000)
    if validar_vista_crear_solicitud_por_ui(page, timeout_ms=2600):
        logger.info("Vista CREAR SOLICITUD confirmada por UI")
    else:
        logger.warning("No se pudo confirmar la vista CREAR SOLICITUD por UI tras la navegación")
    logger.info("Click en CREAR SOLICITUD")


def preparar_flujo_emision_carnet(logger: logging.Logger, page, grupo: str) -> None:
    logger.info("Login correcto para grupo %s. Continúa el flujo de emisión de carnet.", grupo)
    navegar_dssp_carne_crear_solicitud(page, logger)
    logger.info("URL post-login: %s", page.url)


def resolver_grupos_objetivo() -> list:
    grupos_env = str(os.getenv("CARNET_GRUPOS", "SELVA,JV") or "SELVA,JV")
    grupos = [x.strip().upper() for x in grupos_env.split(",") if x.strip()]
    salida = []
    for g in grupos:
        if g in {"SELVA", "JV"} and g not in salida:
            salida.append(g)
    return salida or ["JV"]


def credenciales_por_grupo(grupo: str) -> dict:
    if grupo == "SELVA":
        return CREDENCIALES_SELVA
    return CREDENCIALES_JV


def ejecutar_login_grupo(playwright, logger: logging.Logger, grupo: str):
    credenciales = credenciales_por_grupo(grupo)
    validar_credenciales_configuradas(credenciales, grupo)

    hold_browser_open = _as_bool_env("HOLD_BROWSER_OPEN", default=False)
    headless = _as_bool_env("CARNET_HEADLESS", default=False)
    login_validation_timeout_ms = max(1000, _safe_int_env("LOGIN_VALIDATION_TIMEOUT_MS", 12000))

    browser = None
    context = None
    try:
        launch_args = _build_launch_args_for_window()
        logger.info("[%s] Args Chromium: %s", grupo, " ".join(launch_args))
        browser = playwright.chromium.launch(
            headless=headless,
            slow_mo=0,
            args=launch_args,
        )
        context = browser.new_context(no_viewport=True, ignore_https_errors=True)
        page = context.new_page()

        logger.info("[%s] Navegando a login", grupo)
        page.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=45000)
        esperar_hasta_servicio_disponible(page, URL_LOGIN, espera_segundos=8)

        activar_pestana_autenticacion_tradicional(page)
        page.locator(SEL["numero_documento"]).wait_for(state="visible", timeout=9000)

        page.select_option(SEL["tipo_doc_select"], value=credenciales["tipo_documento_valor"])
        page.wait_for_timeout(300)

        escribir_input_rapido(page, SEL["numero_documento"], credenciales["numero_documento"])
        escribir_input_rapido(page, SEL["usuario"], credenciales["usuario"])
        escribir_input_rapido(page, SEL["clave"], credenciales["contrasena"])
        logger.info("[%s] Credenciales cargadas", grupo)

        captcha_text = solve_captcha_ocr(page, logger)
        escribir_input_rapido(page, SEL["captcha_input"], captcha_text)
        logger.info("[%s] Captcha escrito automáticamente", grupo)

        page.locator(SEL["ingresar"]).click(timeout=10000)
        ok, msg_error, tiempo = validar_resultado_login_por_ui(page, timeout_ms=login_validation_timeout_ms)
        if not ok:
            raise Exception(f"[{grupo}] Login fallido: {msg_error}")

        logger.info("[%s] Login exitoso en %.2fs", grupo, tiempo)
        preparar_flujo_emision_carnet(logger, page, grupo)

        if hold_browser_open and not _is_scheduled_mode():
            logger.info("[%s] HOLD_BROWSER_OPEN=1. Esperando Ctrl+C", grupo)
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                logger.info("[%s] Interrupción manual detectada", grupo)
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


def ejecutar_flujo_secundario() -> int:
    worker_id = str(os.getenv("WORKER_ID", "main") or "main")
    child_suffix = f"worker_{worker_id}" if _as_bool_env("MULTIWORKER_CHILD", default=False) else "main"
    logger = setup_logger("carnet_emision", suffix=child_suffix)
    logger.info("INICIANDO FLUJO CARNET - Login automático")

    if _as_bool_env("CARNET_SHEET_PRINT_SAMPLE", default=True):
        try:
            imprimir_muestra_google_sheet(
                logger,
                max_rows=max(1, _safe_int_env("CARNET_SHEET_SAMPLE_ROWS", 5)),
            )
        except Exception as exc:
            logger.warning("No se pudo leer Google Sheet de muestra: %s", exc)

    if _as_bool_env("CARNET_SHEET_DEMO_ONLY", default=False):
        logger.info("CARNET_SHEET_DEMO_ONLY=1 -> finaliza tras imprimir muestra del Google Sheet")
        return 0

    grupos = resolver_grupos_objetivo()
    group_override = str(os.getenv("WORKER_GROUP", "") or "").strip().upper()
    if group_override:
        grupos = [group_override]

    max_login_retries_per_group = max(1, _safe_int_env("MAX_LOGIN_RETRIES_PER_GROUP", 12))

    playwright = sync_playwright().start()
    try:
        for grupo in grupos:
            intento = 0
            while intento < max_login_retries_per_group:
                intento += 1
                logger.info("[%s] Intento login %s/%s", grupo, intento, max_login_retries_per_group)
                try:
                    ejecutar_login_grupo(playwright, logger, grupo)
                    break
                except PlaywrightTimeoutError as exc:
                    logger.warning("[%s] Timeout en intento %s: %s", grupo, intento, exc)
                except Exception as exc:
                    logger.warning("[%s] Error en intento %s: %s", grupo, intento, exc)

                if intento >= max_login_retries_per_group:
                    raise Exception(f"[{grupo}] No se pudo completar login tras {max_login_retries_per_group} intentos")
                time.sleep(min(8, 1 + intento))

        logger.info("Flujo finalizado correctamente")
        return 0
    except Exception as exc:
        logger.exception("Fallo general del flujo: %s", exc)
        return 1
    finally:
        try:
            playwright.stop()
        except Exception:
            pass
        logger.info("Navegador cerrado")


def _build_units_for_workers() -> list:
    grupos = resolver_grupos_objetivo()
    units = []
    for g in grupos:
        creds = credenciales_por_grupo(g)
        if creds.get("numero_documento") and creds.get("usuario") and creds.get("contrasena"):
            units.append({"grupo": g})
    return units


def _run_worker_unit(worker_id: int, unit: dict, workers: int, screen_w_eff: int, screen_h_eff: int, logger: logging.Logger) -> int:
    grupo = unit["grupo"]
    env = os.environ.copy()
    env["MULTIWORKER_CHILD"] = "1"
    env["WORKER_ID"] = str(worker_id)
    env["WORKER_GROUP"] = grupo
    env["BROWSER_TILE_ENABLE"] = "1"
    env["BROWSER_TILE_TOTAL"] = str(workers)
    env["BROWSER_TILE_INDEX"] = str(worker_id - 1)
    env["BROWSER_TILE_SCREEN_W"] = str(_safe_int_env("BROWSER_TILE_SCREEN_W", screen_w_eff))
    env["BROWSER_TILE_SCREEN_H"] = str(_safe_int_env("BROWSER_TILE_SCREEN_H", screen_h_eff))
    env["BROWSER_TILE_TOP_OFFSET"] = str(_safe_int_env("BROWSER_TILE_TOP_OFFSET", 0))
    env["BROWSER_TILE_GAP"] = str(_safe_int_env("BROWSER_TILE_GAP", 6))
    env["BROWSER_TILE_FRAME_PAD"] = str(_safe_int_env("BROWSER_TILE_FRAME_PAD", 2))

    cmd = [sys.executable, str(BASE_DIR / "carnet_emision.py")]
    logger.info("[W%s] Ejecutando grupo %s", worker_id, grupo)

    proc = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    worker_log = LOGS_DIR / f"worker_{worker_id}_{grupo}_{stamp}.log"
    worker_log.write_text(
        "# STDOUT\n"
        + (proc.stdout or "")
        + "\n\n# STDERR\n"
        + (proc.stderr or ""),
        encoding="utf-8",
    )

    if proc.returncode != 0:
        logger.error("[W%s] Grupo %s falló con exit_code=%s | log=%s", worker_id, grupo, proc.returncode, worker_log)
    else:
        logger.info("[W%s] Grupo %s OK | log=%s", worker_id, grupo, worker_log)
    return proc.returncode


def _ejecutar_scheduled_multihilo_orquestador() -> int:
    logger = setup_logger("carnet_emision_multi", suffix="orchestrator")
    workers = max(1, min(4, _safe_int_env("SCHEDULED_WORKERS", 2)))
    screen_w_eff, screen_h_eff = _detect_windows_screen_size()
    units = _build_units_for_workers()
    if not units:
        logger.error("No hay unidades para workers. Revisa credenciales por grupo en .env")
        return 1

    logger.info(
        "SCHEDULED_MULTIWORKER activado | workers=%s | units=%s | pantalla_efectiva=%sx%s",
        workers,
        len(units),
        screen_w_eff,
        screen_h_eff,
    )
    q = queue.Queue()
    for unit in units:
        q.put(unit)

    lock = queue.Queue()
    results = []

    def worker_loop(worker_id: int):
        processed = 0
        while True:
            try:
                unit = q.get_nowait()
            except Exception:
                break
            code = _run_worker_unit(worker_id, unit, workers, screen_w_eff, screen_h_eff, logger)
            results.append({"worker": worker_id, "grupo": unit.get("grupo", ""), "exit_code": code})
            processed += 1
        lock.put(processed)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(worker_loop, wid) for wid in range(1, workers + 1)]
        for f in futures:
            f.result()

    counts = []
    while not lock.empty():
        counts.append(lock.get())
    logger.info("Conteo por worker: %s", counts)

    failed = [r for r in results if int(r.get("exit_code", 1)) != 0]
    if failed:
        logger.error("Workers con fallo: %s", len(failed))
        for r in failed:
            logger.error("[W%s] grupo=%s exit=%s", r["worker"], r["grupo"], r["exit_code"])
        return 1

    logger.info("Orquestador multihilo finalizado sin fallos")
    return 0


def main() -> int:
    if _multiworker_habilitado():
        return _ejecutar_scheduled_multihilo_orquestador()
    return ejecutar_flujo_secundario()


if __name__ == "__main__":
    raise SystemExit(main())
