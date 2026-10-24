from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from .models import Channel

SUFFIX_NOISE_RE = re.compile(
    r"\s*(\(\d+\)|\[backup\]|\[mirror\]|\[alt\]|\(backup\)|\(mirror\))\s*$",
    re.IGNORECASE,
)
QUALITY_LABEL_RE = re.compile(r"\s*\(\d{3,4}p\)\s*", re.IGNORECASE)
STATUS_LABEL_RE = re.compile(
    r"\s*\[(Not 24/7|Geo-blocked|Offline|Timeout)\]\s*",
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = QUALITY_LABEL_RE.sub(" ", text)
    text = STATUS_LABEL_RE.sub(" ", text)
    text = SUFFIX_NOISE_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def is_spanish_speaking(
    channel: Channel,
    allowed_countries: set[str],
) -> bool:
    lang = (channel.language or "").lower()
    if lang in {"spa", "es", "spanish", "español", "espanol"}:
        return True
    if "spa" in lang.split(";") or "es" in lang.split(";"):
        return True
    # Playlist spa.m3u already is Spanish-language; keep entries with known ES countries
    if channel.country and channel.country.upper() in allowed_countries:
        return True
    # spa.m3u entries without country still count as Spanish
    if not channel.country:
        return True
    return channel.country.upper() in allowed_countries


def drop_low_quality_flags(channel: Channel, strict: bool = False) -> bool:
    name = channel.name.lower()
    if "[offline]" in name or "[timeout]" in name:
        return False
    if strict and "[geo-blocked]" in name:
        return False
    return True


def prefer_better(a: Channel, b: Channel) -> Channel:
    """Pick the better of two duplicate candidates."""
    score_a = (
        a.quality_score,
        1 if a.tvg_id else 0,
        1 if a.tvg_logo else 0,
        1 if a.url.startswith("https://") else 0,
        -len(a.name),
    )
    score_b = (
        b.quality_score,
        1 if b.tvg_id else 0,
        1 if b.tvg_logo else 0,
        1 if b.url.startswith("https://") else 0,
        -len(b.name),
    )
    return a if score_a >= score_b else b


def deduplicate(channels: list[Channel]) -> list[Channel]:
    by_url: dict[str, Channel] = {}
    for ch in channels:
        key = ch.url.strip()
        if key in by_url:
            by_url[key] = prefer_better(by_url[key], ch)
        else:
            by_url[key] = ch

    by_id: dict[str, Channel] = {}
    no_id: list[Channel] = []
    for ch in by_url.values():
        if ch.tvg_id:
            tid = ch.tvg_id.strip()
            if tid in by_id:
                by_id[tid] = prefer_better(by_id[tid], ch)
            else:
                by_id[tid] = ch
        else:
            no_id.append(ch)

    by_name: dict[str, Channel] = {}
    for ch in list(by_id.values()) + no_id:
        # Same country + same normalized name = duplicate brand
        key = f"{ch.country}|{normalize_name(ch.name)}"
        if key in by_name:
            by_name[key] = prefer_better(by_name[key], ch)
        else:
            by_name[key] = ch

    return list(by_name.values())


def assign_groups(
    channels: list[Channel],
    mapping: dict,
) -> list[Channel]:
    rules = mapping.get("rules", [])
    country_names: dict[str, str] = mapping.get("country_names", {})
    compiled = [
        (re.compile("|".join(rule["match"]), re.IGNORECASE), rule["group"])
        for rule in rules
    ]

    for ch in channels:
        haystack = f"{ch.group_title} {ch.name}".lower()
        matched = None
        for pattern, group in compiled:
            if pattern.search(haystack):
                matched = group
                break

        country_label = country_names.get(ch.country.upper(), ch.country or "Internacional")
        if matched:
            ch.group_title = f"{matched} | {country_label}"
        else:
            ch.group_title = f"Nacionales | {country_label}"
    return channels


def sort_channels(channels: list[Channel], mapping: dict) -> list[Channel]:
    order = mapping.get("group_order", [])
    # Extract base category before " | "
    def base_group(title: str) -> str:
        return title.split("|", 1)[0].strip()

    rank = {name: idx for idx, name in enumerate(order)}

    def sort_key(ch: Channel):
        bg = base_group(ch.group_title)
        return (
            rank.get(bg, 999),
            ch.group_title,
            normalize_name(ch.name),
            -ch.quality_score,
        )

    return sorted(channels, key=sort_key)


def filter_channels(
    channels: list[Channel],
    allowed_countries: set[str],
    mapping: dict,
    strict_geo: bool = False,
) -> list[Channel]:
    kept = [
        ch
        for ch in channels
        if is_spanish_speaking(ch, allowed_countries) and drop_low_quality_flags(ch, strict_geo)
    ]
    kept = deduplicate(kept)
    kept = assign_groups(kept, mapping)
    return sort_channels(kept, mapping)


def summarize_by_country(channels: list[Channel]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for ch in channels:
        counts[ch.country or "??"] += 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))
