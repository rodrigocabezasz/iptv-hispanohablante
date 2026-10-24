from __future__ import annotations

from pathlib import Path

from .models import Channel


def build_m3u(channels: list[Channel], epg_url: str | None = None) -> str:
    lines: list[str] = ["#EXTM3U"]
    if epg_url:
        lines[0] = f'#EXTM3U url-tvg="{epg_url}"'

    for ch in channels:
        attrs = [
            f'tvg-id="{ch.tvg_id}"' if ch.tvg_id else 'tvg-id=""',
            f'tvg-name="{_xml_escape(ch.display_name)}"',
        ]
        if ch.tvg_logo:
            attrs.append(f'tvg-logo="{ch.tvg_logo}"')
        if ch.group_title:
            attrs.append(f'group-title="{_xml_escape(ch.group_title)}"')

        lines.append(f'#EXTINF:-1 {" ".join(attrs)},{ch.display_name}')
        lines.extend(ch.vlc_opts)
        lines.append(ch.url)

    return "\n".join(lines) + "\n"


def write_m3u(channels: list[Channel], path: Path, epg_url: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_m3u(channels, epg_url=epg_url), encoding="utf-8")
    return path


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
