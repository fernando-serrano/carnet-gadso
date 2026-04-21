import argparse
import os

from app import carnet_emision as core

from .runtime import ejecutar_con_sesion_autenticada


def _accion_bandeja(page, logger, _grupo: str) -> None:
    core.navegar_dssp_carne_bandeja_carnes(page, logger)

    estado_objetivo = str(os.getenv("CARNET_BANDEJA_ESTADO_OBJETIVO", "") or "").strip()
    if estado_objetivo:
        core.seleccionar_estado_bandeja(page, logger, estado_objetivo=estado_objetivo)

    logger.info("[BANDEJA] Vista de BANDEJA DE EMISION cargada. URL actual: %s", page.url)


def ejecutar_bandeja(grupo: str, keep_open: bool = False) -> int:
    return ejecutar_con_sesion_autenticada(
        grupo=grupo,
        logger_suffix="segment_bandeja",
        accion=_accion_bandeja,
        keep_browser_open_on_finish=keep_open,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ejecuta login y acceso a la bandeja de carnets"
    )
    parser.add_argument("--grupo", default="JV", help="Grupo objetivo (JV o SELVA)")
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Mantiene el navegador abierto al finalizar",
    )
    args = parser.parse_args()
    return ejecutar_bandeja(grupo=str(args.grupo).strip().upper(), keep_open=bool(args.keep_open))


if __name__ == "__main__":
    raise SystemExit(main())
