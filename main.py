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
from src.filter import (
    deduplicate,
    process_all_sources,
    sort_channels,
    summarize_by_country,
    summarize_by_group,
)
from src.health_check import check_channels, keep_healthy
from src.parser import parse_m3u
from src.report import write_health_report

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
DATA_RAW = ROOT / "data" / "raw"
DATA_CACHE = ROOT / "data" / "cache"
DIST = ROOT / "dist"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_epg_urls(sources: dict) -> list[str]:
    template = sources["epg_url_template"]
    return [template.format(code=code) for code in sources["epg_countries"]]


def run(
    skip_epg: bool = False,
    epg_public_url: str | None = None,
    health_check: bool = False,
    keep_unhealthy: bool = False,
) -> None:
    sources = load_json(CONFIG_DIR / "sources.json")
    mapping = load_json(CONFIG_DIR / "categories_mapping.json")
    allowed = {c.upper() for c in sources["spanish_speaking_countries"]}
    keywords = sources.get("spanish_keywords", [])
    hc_cfg = sources.get("health_check", {})

    DATA_RAW.mkdir(parents=True, exist_ok=True)
    DATA_CACHE.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)

    print("==> Descargando playlists M3U...")
    all_channels = []
    for playlist in sources["playlists"]:
        raw_path = DATA_RAW / f"{playlist['name']}.m3u"
        try:
            content = download_text(playlist["url"], dest=raw_path)
        except Exception as exc:  # noqa: BLE001
            print(f"  [aviso] {playlist['name']}: no se pudo descargar ({exc})")
            continue
        parsed = parse_m3u(content)
        for ch in parsed:
            ch.source_name = playlist["name"]
            ch.kind = playlist.get("kind", "live")
        print(f"  {playlist['name']}: {len(parsed)} canales")
        all_channels.extend(parsed)

    print("==> Filtrando (español/LATAM + FAST), deduplicando y ordenando...")
    channels = process_all_sources(
        all_channels,
        allowed,
        mapping,
        keywords,
        sources["playlists"],
        strict_geo=False,
    )
    print(f"  Resultado: {len(channels)} canales únicos")
    print("  Por grupo:")
    for group, count in summarize_by_group(channels).items():
        print(f"    {group}: {count}")
    print("  Por país (live/movies/series):")
    for country, count in list(summarize_by_country(channels).items())[:15]:
        print(f"    {country}: {count}")

    if health_check:
        print("==> Verificando disponibilidad de streams (health-check)...")
        channels = check_channels(
            channels,
            timeout=float(hc_cfg.get("timeout_seconds", 6)),
            max_workers=int(hc_cfg.get("max_workers", 40)),
            bytes_to_read=int(hc_cfg.get("bytes_to_read", 2048)),
            cache_path=DATA_CACHE / "health.json",
            cache_hours=float(hc_cfg.get("cache_hours", 12)),
        )
        write_health_report(
            channels,
            DIST / "health_report.json",
            DIST / "health_report.html",
        )
        ok = sum(1 for c in channels if c.health_ok)
        fail = sum(1 for c in channels if c.health_ok is False)
        print(f"  OK={ok} | FAIL={fail}")
        print(f"  Reporte: {DIST / 'health_report.html'}")
        if not keep_unhealthy:
            before = len(channels)
            channels = keep_healthy(channels)
            print(f"  Lista final solo OK: {len(channels)} (antes {before})")

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
    print(f"==> Lista lista: {out_m3u} ({len(channels)} canales)")
    print("Listo.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Genera lista IPTV hispana + FAST + EPG para TiviMate"
    )
    parser.add_argument("--skip-epg", action="store_true", help="Solo generar M3U")
    parser.add_argument(
        "--epg-url",
        default=None,
        help="URL pública del EPG para url-tvg del M3U",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Probar streams y generar health_report.html (recomendado en tu PC)",
    )
    parser.add_argument(
        "--keep-unhealthy",
        action="store_true",
        help="Con --health-check, no borrar canales caídos de la lista",
    )
    args = parser.parse_args(argv)
    try:
        run(
            skip_epg=args.skip_epg,
            epg_public_url=args.epg_url,
            health_check=args.health_check,
            keep_unhealthy=args.keep_unhealthy,
        )
    except KeyboardInterrupt:
        print("Cancelado.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
