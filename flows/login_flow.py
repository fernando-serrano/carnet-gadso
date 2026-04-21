import argparse

from .runtime import ejecutar_con_sesion_autenticada


def ejecutar_login(grupo: str, keep_open: bool = False) -> int:
    return ejecutar_con_sesion_autenticada(
        grupo=grupo,
        logger_suffix="segment_login",
        accion=lambda page, logger, _grupo: logger.info(
            "[LOGIN] Login completado. URL actual: %s", page.url
        ),
        keep_browser_open_on_finish=keep_open,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ejecuta solo el bloque de autenticacion SEL para carnet"
    )
    parser.add_argument("--grupo", default="JV", help="Grupo objetivo (JV o SELVA)")
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Mantiene el navegador abierto al finalizar",
    )
    args = parser.parse_args()
    return ejecutar_login(grupo=str(args.grupo).strip().upper(), keep_open=bool(args.keep_open))


if __name__ == "__main__":
    raise SystemExit(main())
