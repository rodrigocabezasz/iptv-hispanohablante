from __future__ import annotations

import re
from typing import Iterator

from .models import Channel

ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
QUALITY_RE = re.compile(r"\((\d{3,4})p\)", re.IGNORECASE)
COUNTRY_FROM_ID_RE = re.compile(r"\.([a-z]{2})(?:@|$)", re.IGNORECASE)


def _parse_attrs(extinf_line: str) -> dict[str, str]:
    return {k.lower(): v for k, v in ATTR_RE.findall(extinf_line)}


def _extract_name(extinf_line: str) -> str:
    if "," not in extinf_line:
        return "Unknown"
    return extinf_line.split(",", 1)[1].strip()


def _quality_score(name: str) -> int:
    match = QUALITY_RE.search(name)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _infer_country(attrs: dict[str, str], tvg_id: str) -> str:
    for key in ("tvg-country", "group-country", "country"):
        raw = attrs.get(key, "").strip()
        if raw:
            # iptv-org sometimes uses semicolon-separated codes
            return raw.split(";")[0].upper()
    match = COUNTRY_FROM_ID_RE.search(tvg_id)
    if match:
        return match.group(1).upper()
    return ""


def parse_m3u(content: str) -> list[Channel]:
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    channels: list[Channel] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("#EXTINF"):
            i += 1
            continue

        attrs = _parse_attrs(line)
        name = _extract_name(line)
        vlc_opts: list[str] = []
        i += 1
        while i < len(lines) and lines[i].startswith("#"):
            if lines[i].startswith("#EXTVLCOPT") or lines[i].startswith("#EXTGRP"):
                vlc_opts.append(lines[i])
            i += 1

        if i >= len(lines) or lines[i].startswith("#"):
            continue

        url = lines[i]
        i += 1
        tvg_id = attrs.get("tvg-id", "")
        country = _infer_country(attrs, tvg_id)
        language = attrs.get("tvg-language", attrs.get("language", ""))

        channels.append(
            Channel(
                name=name,
                url=url,
                tvg_id=tvg_id,
                tvg_logo=attrs.get("tvg-logo", ""),
                group_title=attrs.get("group-title", ""),
                country=country,
                language=language,
                extra_attrs=attrs,
                vlc_opts=vlc_opts,
                quality_score=_quality_score(name),
            )
        )
    return channels


def iter_channel_blocks(content: str) -> Iterator[tuple[str, str]]:
    """Utility for debugging: yields (extinf, url)."""
    for ch in parse_m3u(content):
        yield ch.name, ch.url
