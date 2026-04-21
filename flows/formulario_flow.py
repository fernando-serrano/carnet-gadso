import argparse

import carnet_emision as core

from .runtime import ejecutar_con_sesion_autenticada


def _accion_formulario(page, logger, _grupo: str) -> None:
    core.navegar_dssp_carne_crear_solicitud(page, logger)
    logger.info("[FORMULARIO] Vista de CREAR SOLICITUD cargada. URL actual: %s", page.url)


def ejecutar_formulario(grupo: str, keep_open: bool = False) -> int:
    return ejecutar_con_sesion_autenticada(
        grupo=grupo,
        logger_suffix="segment_formulario",
        accion=_accion_formulario,
        keep_browser_open_on_finish=keep_open,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ejecuta login y acceso a la vista CREAR SOLICITUD"
    )
    parser.add_argument("--grupo", default="JV", help="Grupo objetivo (JV o SELVA)")
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Mantiene el navegador abierto al finalizar",
    )
    args = parser.parse_args()
    return ejecutar_formulario(grupo=str(args.grupo).strip().upper(), keep_open=bool(args.keep_open))


if __name__ == "__main__":
    raise SystemExit(main())
