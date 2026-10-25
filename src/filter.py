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


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def matches_spanish_keywords(channel: Channel, keywords: list[str]) -> bool:
    haystack = _fold(f"{channel.name} {channel.group_title} {channel.tvg_id} {channel.language}")
    return any(_fold(kw) in haystack for kw in keywords)


def is_spanish_country(channel: Channel, allowed_countries: set[str]) -> bool:
    if channel.country and channel.country.upper() in allowed_countries:
        return True
    return False


def is_spanish_speaking(
    channel: Channel,
    allowed_countries: set[str],
) -> bool:
    lang = (channel.language or "").lower()
    if lang in {"spa", "es", "spanish", "español", "espanol"}:
        return True
    if "spa" in lang.split(";") or "es" in lang.split(";"):
        return True
    if channel.country and channel.country.upper() in allowed_countries:
        return True
    if not channel.country:
        return True
    return channel.country.upper() in allowed_countries


def keep_channel(
    channel: Channel,
    filter_mode: str,
    allowed_countries: set[str],
    keywords: list[str],
) -> bool:
    if filter_mode == "spanish_playlist":
        return is_spanish_speaking(channel, allowed_countries)
    if filter_mode == "spanish_country_or_keywords":
        return is_spanish_country(channel, allowed_countries) or matches_spanish_keywords(
            channel, keywords
        )
    if filter_mode == "spanish_keywords":
        return matches_spanish_keywords(channel, keywords)
    if filter_mode == "all":
        return True
    return is_spanish_speaking(channel, allowed_countries)


def drop_low_quality_flags(channel: Channel, strict: bool = False) -> bool:
    name = channel.name.lower()
    if "[offline]" in name or "[timeout]" in name:
        return False
    if strict and "[geo-blocked]" in name:
        return False
    return True


def prefer_better(a: Channel, b: Channel) -> Channel:
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
        key = f"{ch.kind}|{ch.country}|{normalize_name(ch.name)}"
        if key in by_name:
            by_name[key] = prefer_better(by_name[key], ch)
        else:
            by_name[key] = ch

    return list(by_name.values())


# Categories that stay as a single global list (no country split).
_FLAT_GROUPS = {
    "Deportes",
    "Entretenimiento",
    "Cine",
    "Series",
    "Infantiles",
    "Documentales",
    "Música",
    "Religión",
    "Clima",
    "Compras",
}

# Nacionales + Noticias collapse into the country name alone (Chile, Perú, …).
_COUNTRY_BUCKETS = {"General", "Noticias", "Nacionales"}


def _country_display_name(channel: Channel, mapping: dict) -> str | None:
    code = (channel.country or "").upper().strip()
    if not code:
        return None
    names = mapping.get("country_names", {})
    return names.get(code)


def assign_groups(
    channels: list[Channel],
    mapping: dict,
    group_prefix_by_source: dict[str, str] | None = None,
) -> list[Channel]:
    """Assign groups: thematic flats + country-only buckets for nacionales/noticias."""
    rules = mapping.get("rules", [])
    default_group = mapping.get("defaults", {}).get("unknown", "General")
    compiled = [
        (re.compile("|".join(rule["match"]), re.IGNORECASE), rule["group"])
        for rule in rules
    ]
    # group_prefix_by_source kept for API compat; unused with flat+country scheme.
    _ = group_prefix_by_source or {}

    for ch in channels:
        if ch.kind == "movies":
            ch.group_title = "Cine"
            continue
        if ch.kind == "series":
            ch.group_title = "Series"
            continue

        haystack = f"{ch.group_title} {ch.name}".lower()
        matched = None
        for pattern, group in compiled:
            if pattern.search(haystack):
                matched = group
                break
        group = matched or default_group

        if group in _FLAT_GROUPS:
            ch.group_title = group
            continue

        # General / Noticias / Nacionales → just the country name.
        if group in _COUNTRY_BUCKETS:
            country_name = _country_display_name(ch, mapping)
            ch.group_title = country_name or "General"
            continue

        ch.group_title = group
    return channels


def sort_channels(channels: list[Channel], mapping: dict) -> list[Channel]:
    order = list(mapping.get("group_order", []))
    # Insert country names after Favoritos / before thematic groups.
    country_names = list(mapping.get("country_names", {}).values())
    insert_at = 1 if order and order[0] == "Favoritos" else 0
    # Drop legacy Nacionales/Noticias placeholders from order.
    order = [g for g in order if g not in {"Nacionales", "Noticias"}]
    # Avoid duplicating General if countries already cover most channels.
    for name in reversed(country_names):
        if name not in order:
            order.insert(insert_at, name)

    rank = {name: idx for idx, name in enumerate(order)}

    def sort_key(ch: Channel):
        return (
            rank.get(ch.group_title, 999),
            ch.group_title,
            normalize_name(ch.name),
            -ch.quality_score,
        )

    return sorted(channels, key=sort_key)


def filter_channels(
    channels: list[Channel],
    allowed_countries: set[str],
    mapping: dict,
    keywords: list[str],
    filter_mode: str = "spanish_playlist",
    group_prefix: str | None = None,
    strict_geo: bool = False,
) -> list[Channel]:
    kept = [
        ch
        for ch in channels
        if keep_channel(ch, filter_mode, allowed_countries, keywords)
        and drop_low_quality_flags(ch, strict_geo)
    ]
    prefix_map = {ch.source_name: group_prefix for ch in kept if group_prefix}
    kept = deduplicate(kept)
    kept = assign_groups(kept, mapping, group_prefix_by_source=prefix_map)
    return sort_channels(kept, mapping)


def process_all_sources(
    channels: list[Channel],
    allowed_countries: set[str],
    mapping: dict,
    keywords: list[str],
    playlist_meta: list[dict],
    strict_geo: bool = False,
) -> list[Channel]:
    meta_by_name = {p["name"]: p for p in playlist_meta}
    buckets: list[Channel] = []
    prefixes: dict[str, str] = {}

    for ch in channels:
        meta = meta_by_name.get(ch.source_name, {})
        mode = meta.get("filter", "spanish_playlist")
        if not keep_channel(ch, mode, allowed_countries, keywords):
            continue
        if not drop_low_quality_flags(ch, strict_geo):
            continue
        if meta.get("group_prefix"):
            prefixes[ch.source_name] = meta["group_prefix"]
        buckets.append(ch)

    buckets = deduplicate(buckets)
    buckets = assign_groups(buckets, mapping, group_prefix_by_source=prefixes)
    return sort_channels(buckets, mapping)


def summarize_by_country(channels: list[Channel]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for ch in channels:
        counts[ch.country or "??"] += 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))


def summarize_by_group(channels: list[Channel]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for ch in channels:
        base = ch.group_title.split("|", 1)[0].strip() if ch.group_title else "Otros"
        counts[base] += 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))
