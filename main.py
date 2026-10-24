from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.builder import write_m3u
from src.downloader import download_many, download_text
from src.epg_matcher import (
    align_channels_to_epg,
    coverage_report,
    filter_epg_files,
    load_epg_channel_ids,
)
from src.filter import deduplicate, filter_channels, sort_channels, summarize_by_country
from src.parser import parse_m3u

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
DATA_RAW = ROOT / "data" / "raw"
DIST = ROOT / "dist"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_epg_urls(sources: dict) -> list[str]:
    template = sources["epg_url_template"]
    return [template.format(code=code) for code in sources["epg_countries"]]


def run(skip_epg: bool = False, epg_public_url: str | None = None) -> None:
    sources = load_json(CONFIG_DIR / "sources.json")
    mapping = load_json(CONFIG_DIR / "categories_mapping.json")
    allowed = {c.upper() for c in sources["spanish_speaking_countries"]}

    DATA_RAW.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)

    print("==> Descargando playlists M3U...")
    all_channels = []
    for playlist in sources["playlists"]:
        raw_path = DATA_RAW / f"{playlist['name']}.m3u"
        content = download_text(playlist["url"], dest=raw_path)
        parsed = parse_m3u(content)
        print(f"  {playlist['name']}: {len(parsed)} canales")
        all_channels.extend(parsed)

    print("==> Filtrando, deduplicando y ordenando...")
    channels = filter_channels(all_channels, allowed, mapping, strict_geo=False)
    print(f"  Resultado: {len(channels)} canales únicos")
    print("  Por país:")
    for country, count in summarize_by_country(channels).items():
        print(f"    {country}: {count}")

    epg_url_for_header = epg_public_url
    if not skip_epg:
        print("==> Descargando EPG por países...")
        epg_urls = build_epg_urls(sources)
        epg_dir = DATA_RAW / "epg"
        epg_paths = download_many(epg_urls, epg_dir)
        print(f"  EPG descargados: {len(epg_paths)}")

        print("==> Alineando tvg-id con EPG...")
        epg_ids = load_epg_channel_ids(epg_paths)
        aligned = align_channels_to_epg(channels, epg_ids)
        # Tras quitar sufijos @SD/@HD pueden quedar duplicados reales
        before = len(channels)
        channels = sort_channels(deduplicate(channels), mapping)
        print(
            f"  IDs EPG: {len(epg_ids)} | alineados: {aligned} | "
            f"canales tras re-dedupe: {len(channels)} (antes {before})"
        )

        wanted = {ch.tvg_id for ch in channels if ch.tvg_id} & epg_ids
        out_xml = DIST / "epg_hispanohablante.xml"
        print("==> Filtrando EPG a canales de la lista...")
        n_ch, n_prog = filter_epg_files(epg_paths, wanted, out_xml)
        print(f"  Canales EPG: {n_ch} | Programas: {n_prog}")
        print(f"  Escrito: {out_xml}")
        print(f"  Escrito: {out_xml.name}.gz")

        report = coverage_report(channels, wanted)
        print(
            f"  Cobertura EPG: {report['epg_matched']}/{report['with_tvg_id']} "
            f"con tvg-id ({report['total']} canales totales)"
        )

        if not epg_url_for_header:
            epg_url_for_header = "epg_hispanohablante.xml.gz"

    out_m3u = DIST / "lista_tivimate.m3u"
    write_m3u(channels, out_m3u, epg_url=epg_url_for_header)
    print(f"==> Lista lista: {out_m3u}")
    print("Listo.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera lista IPTV hispana + EPG para TiviMate")
    parser.add_argument("--skip-epg", action="store_true", help="Solo generar M3U")
    parser.add_argument(
        "--epg-url",
        default=None,
        help="URL pública del EPG para poner en la cabecera url-tvg del M3U",
    )
    args = parser.parse_args(argv)
    try:
        run(skip_epg=args.skip_epg, epg_public_url=args.epg_url)
    except KeyboardInterrupt:
        print("Cancelado.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
