from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .models import Channel


def write_health_report(channels: list[Channel], out_json: Path, out_html: Path) -> None:
    rows = [
        {
            "name": ch.display_name,
            "group": ch.group_title,
            "kind": ch.kind,
            "country": ch.country,
            "source": ch.source_name,
            "url": ch.url,
            "ok": ch.health_ok,
            "detail": ch.health_detail,
            "tvg_id": ch.tvg_id,
        }
        for ch in channels
    ]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(rows),
        "ok": sum(1 for r in rows if r["ok"] is True),
        "fail": sum(1 for r in rows if r["ok"] is False),
        "unknown": sum(1 for r in rows if r["ok"] is None),
        "by_group": dict(Counter((r["group"] or "").split("|")[0].strip() for r in rows if r["ok"] is True)),
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps({"summary": summary, "channels": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ok_rows = [r for r in rows if r["ok"] is True]
    fail_rows = [r for r in rows if r["ok"] is False]

    def table(items: list[dict], limit: int = 500) -> str:
        parts = [
            "<table><thead><tr><th>Canal</th><th>Grupo</th><th>Fuente</th><th>Detalle</th></tr></thead><tbody>"
        ]
        for r in items[:limit]:
            parts.append(
                "<tr>"
                f"<td>{escape(r['name'])}</td>"
                f"<td>{escape(r['group'] or '')}</td>"
                f"<td>{escape(r['source'] or '')}</td>"
                f"<td>{escape(r['detail'] or '')}</td>"
                "</tr>"
            )
        parts.append("</tbody></table>")
        if len(items) > limit:
            parts.append(f"<p>… y {len(items) - limit} más (ver JSON).</p>")
        return "\n".join(parts)

    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Reporte IPTV – salud de canales</title>
  <style>
    body {{ font-family: Segoe UI, system-ui, sans-serif; margin: 1.5rem; background: #0f1419; color: #e7ecf1; }}
    a {{ color: #7dd3fc; }}
    .ok {{ color: #4ade80; }}
    .fail {{ color: #f87171; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 14px; margin: 1rem 0 2rem; }}
    th, td {{ border-bottom: 1px solid #243041; padding: .45rem .5rem; text-align: left; vertical-align: top; }}
    th {{ position: sticky; top: 0; background: #15202b; }}
    .cards {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
    .card {{ background: #15202b; padding: 1rem 1.2rem; border-radius: 12px; min-width: 140px; }}
  </style>
</head>
<body>
  <h1>Reporte de salud IPTV</h1>
  <p>Generado: {escape(summary["generated_at"])}</p>
  <div class="cards">
    <div class="card">Total<br><strong>{summary["total"]}</strong></div>
    <div class="card ok">OK<br><strong>{summary["ok"]}</strong></div>
    <div class="card fail">Fallan<br><strong>{summary["fail"]}</strong></div>
  </div>
  <p>Abre este HTML en el celular o PC para revisar. Cursor no controla el televisor; este reporte reemplaza esa revisión manual.</p>
  <h2 class="ok">Canales OK ({len(ok_rows)})</h2>
  {table(ok_rows)}
  <h2 class="fail">Canales caídos / no disponibles ({len(fail_rows)})</h2>
  {table(fail_rows)}
</body>
</html>
"""
    out_html.write_text(html, encoding="utf-8")
