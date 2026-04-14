import argparse
import csv
import os
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv


def _normalizar(texto: str) -> str:
    base = str(texto or "").strip().lower()
    base = unicodedata.normalize("NFKD", base)
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", base)


def _build_csv_url(sheet_url: str) -> str:
    raw = str(sheet_url or "").strip()
    if not raw:
        raise ValueError("URL de Google Sheet vacia")

    parsed = urlparse(raw)
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", parsed.path or "")
    if not match:
        raise ValueError("No se pudo extraer sheetId desde la URL")

    sheet_id = match.group(1)
    gid = None
    query = parse_qs(parsed.query or "")
    if query.get("gid"):
        gid = query.get("gid")[0]
    if not gid and parsed.fragment:
        frag = parse_qs(parsed.fragment)
        if frag.get("gid"):
            gid = frag.get("gid")[0]
        elif "gid=" in parsed.fragment:
            gid = parsed.fragment.split("gid=", 1)[1].split("&", 1)[0]

    gid = str(gid or "0").strip() or "0"
    ts = int(time.time() * 1000)
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}&t={ts}"


def _detectar_columna_dni(headers: list[str], prefer_j: bool) -> tuple[int, str, str]:
    if prefer_j and len(headers) >= 10:
        header_j = str(headers[9] or "").strip()
        if _normalizar(header_j) == "dni":
            return 9, header_j, "columna_j"

    for idx, name in enumerate(headers):
        if _normalizar(name) == "dni":
            return idx, str(name or ""), "primer_encabezado_dni"

    raise ValueError("No se encontro columna DNI en el CSV")


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Cachea la hoja base y reporta duplicados de DNI sin afectar el flujo principal."
    )
    parser.add_argument("--url", default="", help="URL de hoja base. Si se omite, usa CARNET_GSHEET_URL")
    parser.add_argument("--cache-dir", default="data/cache", help="Directorio para guardar cache y reporte")
    parser.add_argument("--max-show", type=int, default=30, help="Cantidad maxima de duplicados a mostrar")
    parser.add_argument(
        "--prefer-j",
        action="store_true",
        help="Prioriza columna J como DNI cuando el encabezado de J sea DNI",
    )
    args = parser.parse_args()

    raw_url = str(args.url or os.getenv("CARNET_GSHEET_URL", "") or "").strip()
    if not raw_url:
        raise SystemExit("Falta URL de hoja base (--url o CARNET_GSHEET_URL)")

    csv_url = _build_csv_url(raw_url)
    req = Request(csv_url, headers={"User-Agent": "Mozilla/5.0 (compatible; carnet-dup-check/1.0)"})
    with urlopen(req, timeout=30) as resp:
        content = resp.read()

    text = content.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(text.splitlines()))
    if len(rows) < 2:
        raise SystemExit("CSV sin datos para analizar")

    headers = rows[0]
    dni_idx, dni_header, criterio_col = _detectar_columna_dni(headers, prefer_j=bool(args.prefer_j))

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    cache_file = cache_dir / f"hoja_base_cache_{stamp}.csv"
    cache_file.write_text(text, encoding="utf-8")

    ocurrencias: dict[str, list[int]] = defaultdict(list)
    for row_num, row in enumerate(rows[1:], start=2):
        dni = ""
        if dni_idx < len(row):
            dni = str(row[dni_idx] or "").strip()
        if dni:
            ocurrencias[dni].append(row_num)

    duplicados = [
        {"dni": dni, "cantidad": len(filas), "filas": filas}
        for dni, filas in ocurrencias.items()
        if len(filas) > 1
    ]
    duplicados.sort(key=lambda x: (-int(x["cantidad"]), str(x["dni"])))

    reporte = cache_dir / f"duplicados_dni_{stamp}.csv"
    with reporte.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["dni", "cantidad", "filas"])
        writer.writeheader()
        for item in duplicados:
            writer.writerow(
                {
                    "dni": item["dni"],
                    "cantidad": item["cantidad"],
                    "filas": "|".join(str(x) for x in item["filas"]),
                }
            )

    total_rows = len(rows) - 1
    total_groups = len(duplicados)
    total_rows_dup = sum(int(x["cantidad"]) for x in duplicados)

    print(f"CACHE_FILE={cache_file}")
    print(f"DUPLICATES_REPORT={reporte}")
    print(f"CSV_URL={csv_url}")
    print(f"DNI_COLUMN_INDEX={dni_idx}")
    print(f"DNI_COLUMN_HEADER={dni_header}")
    print(f"DNI_COLUMN_CRITERIO={criterio_col}")
    print(f"TOTAL_ROWS={total_rows}")
    print(f"DUPLICATE_DNI_GROUPS={total_groups}")
    print(f"ROWS_IN_DUPLICATE_GROUPS={total_rows_dup}")

    if total_groups:
        print("TOP_DUPLICATES_START")
        for item in duplicados[: max(1, int(args.max_show))]:
            print(f"DNI={item['dni']};COUNT={item['cantidad']};FILAS={'|'.join(str(x) for x in item['filas'])}")
        print("TOP_DUPLICATES_END")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
