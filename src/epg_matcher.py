from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import Channel


def base_tvg_id(tvg_id: str) -> str:
    """iptv-org streams use Channel.country@Variant; EPG uses Channel.country."""
    if not tvg_id:
        return ""
    return tvg_id.split("@", 1)[0].strip()


def collect_wanted_ids(channels: list[Channel]) -> set[str]:
    wanted: set[str] = set()
    for ch in channels:
        if not ch.tvg_id:
            continue
        wanted.add(ch.tvg_id)
        wanted.add(base_tvg_id(ch.tvg_id))
    return {w for w in wanted if w}


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def load_epg_channel_ids(epg_paths: list[Path]) -> set[str]:
    ids: set[str] = set()
    for path in epg_paths:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for elem in root:
            if _local_tag(elem.tag) == "channel":
                cid = elem.attrib.get("id", "")
                if cid:
                    ids.add(cid)
    return ids


def align_channels_to_epg(channels: list[Channel], epg_ids: set[str]) -> int:
    """Rewrite tvg-id to the form present in EPG when possible."""
    aligned = 0
    for ch in channels:
        if not ch.tvg_id:
            continue
        if ch.tvg_id in epg_ids:
            aligned += 1
            continue
        base = base_tvg_id(ch.tvg_id)
        if base in epg_ids:
            ch.tvg_id = base
            aligned += 1
    return aligned


def filter_epg_files(epg_paths: list[Path], tvg_ids: set[str], out_xml: Path) -> tuple[int, int]:
    """Merge EPG XML files keeping only channels present in the playlist."""
    out_xml.parent.mkdir(parents=True, exist_ok=True)

    kept_channels = 0
    kept_programmes = 0

    root = ET.Element("tv")
    root.set("generator-info-name", "tivimate-hispanohablante")
    seen_channel_ids: set[str] = set()

    for path in epg_paths:
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            print(f"  [aviso] EPG inválido {path.name}: {exc}")
            continue

        src_root = tree.getroot()
        for elem in list(src_root):
            tag = _local_tag(elem.tag)
            if tag == "channel":
                cid = elem.attrib.get("id", "")
                if cid in tvg_ids and cid not in seen_channel_ids:
                    root.append(elem)
                    seen_channel_ids.add(cid)
                    kept_channels += 1
            elif tag == "programme":
                cid = elem.attrib.get("channel", "")
                if cid in tvg_ids:
                    root.append(elem)
                    kept_programmes += 1

    tree_out = ET.ElementTree(root)
    ET.indent(tree_out, space="  ")
    tree_out.write(out_xml, encoding="utf-8", xml_declaration=True)

    gz_path = Path(str(out_xml) + ".gz") if out_xml.suffix != ".gz" else out_xml
    if out_xml.suffix == ".xml":
        gz_path = out_xml.with_name(out_xml.name + ".gz")
    with open(out_xml, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        f_out.writelines(f_in)

    return kept_channels, kept_programmes


def coverage_report(channels: list[Channel], epg_channel_ids: set[str]) -> dict[str, int]:
    with_id = [ch for ch in channels if ch.tvg_id]
    matched = [ch for ch in with_id if ch.tvg_id in epg_channel_ids]
    return {
        "total": len(channels),
        "with_tvg_id": len(with_id),
        "epg_matched": len(matched),
        "epg_missing": len(with_id) - len(matched),
    }
