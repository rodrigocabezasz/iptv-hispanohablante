from __future__ import annotations

import gzip
import ssl
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (compatible; TiviMateListBuilder/1.0)"


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
        return ctx


def download_text(url: str, dest: Path | None = None, timeout: float = 120.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            data = resp.read()
    except ssl.SSLError:
        # Fallback for corporate/local SSL interception environments
        insecure = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=timeout, context=insecure) as resp:
            data = resp.read()

    if url.endswith(".gz") or data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)

    text = data.decode("utf-8", errors="replace")
    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return text


def download_many(urls: list[str], dest_dir: Path) -> list[Path]:
    paths: list[Path] = []
    total = len(urls)
    for idx, url in enumerate(urls, start=1):
        name = url.rstrip("/").split("/")[-1].replace(".gz", "")
        if not name.endswith(".xml"):
            name = f"{name}.xml"
        dest = dest_dir / name
        print(f"  [{idx}/{total}] {name}")
        try:
            download_text(url, dest=dest)
            paths.append(dest)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            print(f"  [aviso] No se pudo descargar {url}: {exc}")
    return paths
