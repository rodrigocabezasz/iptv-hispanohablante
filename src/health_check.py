from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .models import Channel

USER_AGENT = "Mozilla/5.0 (compatible; TiviMateHealthCheck/1.0)"


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl._create_unverified_context()


def _probe_url(url: str, timeout: float, bytes_to_read: int) -> tuple[bool, str]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": USER_AGENT,
            "Range": f"bytes=0-{max(bytes_to_read - 1, 0)}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            chunk = resp.read(bytes_to_read)
            if code and int(code) >= 400:
                return False, f"HTTP {code}"
            if not chunk:
                return False, "empty body"
            return True, f"HTTP {code} ({len(chunk)} B)"
    except urllib.error.HTTPError as exc:
        # Algunos CDN responden 405/501 a Range; reintento simple sin Range
        if exc.code in {405, 416, 501}:
            try:
                req2 = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req2, timeout=timeout, context=_ssl_context()) as resp:
                    chunk = resp.read(bytes_to_read)
                    if chunk:
                        return True, f"HTTP {resp.getcode()} retry"
            except Exception as exc2:  # noqa: BLE001
                return False, str(exc2)[:120]
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:120]


def load_cache(path: Path, max_age_hours: float) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    now = time.time()
    max_age = max_age_hours * 3600
    return {
        url: info
        for url, info in data.get("results", {}).items()
        if now - info.get("checked_at", 0) <= max_age
    }


def save_cache(path: Path, results: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def check_channels(
    channels: list[Channel],
    *,
    timeout: float = 6.0,
    max_workers: int = 40,
    bytes_to_read: int = 2048,
    cache_path: Path | None = None,
    cache_hours: float = 12.0,
) -> list[Channel]:
    cache = load_cache(cache_path, cache_hours) if cache_path else {}
    pending = [ch for ch in channels if ch.url not in cache]
    print(f"  Health-check: {len(channels)} canales | cache hit {len(channels) - len(pending)} | a probar {len(pending)}")

    fresh: dict[str, dict] = {}
    if pending:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_probe_url, ch.url, timeout, bytes_to_read): ch for ch in pending
            }
            done = 0
            total = len(futures)
            for fut in as_completed(futures):
                ch = futures[fut]
                ok, detail = fut.result()
                fresh[ch.url] = {
                    "ok": ok,
                    "detail": detail,
                    "checked_at": time.time(),
                    "name": ch.display_name,
                }
                done += 1
                if done % 50 == 0 or done == total:
                    print(f"    progreso {done}/{total}")

    merged = {**cache, **fresh}
    if cache_path:
        save_cache(cache_path, merged)

    for ch in channels:
        info = merged.get(ch.url, {})
        ch.health_ok = bool(info.get("ok"))
        ch.health_detail = str(info.get("detail", ""))
    return channels


def keep_healthy(channels: list[Channel], keep_unknown: bool = False) -> list[Channel]:
    out: list[Channel] = []
    for ch in channels:
        if ch.health_ok is True:
            out.append(ch)
        elif ch.health_ok is None and keep_unknown:
            out.append(ch)
    return out
