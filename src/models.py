from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Channel:
    name: str
    url: str
    tvg_id: str = ""
    tvg_logo: str = ""
    group_title: str = ""
    country: str = ""
    language: str = ""
    extra_attrs: dict[str, str] = field(default_factory=dict)
    vlc_opts: list[str] = field(default_factory=list)
    quality_score: int = 0

    @property
    def display_name(self) -> str:
        return self.name.strip()
