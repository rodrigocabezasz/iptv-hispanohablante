# IPTV Hispanohablante para TiviMate

Genera una lista M3U limpia (español / Latinoamérica + España) y una EPG filtrada, listas para TiviMate vía **GitHub Pages**.

## URLs para TiviMate (después de publicar)

Sustituye `USUARIO` y `REPO` por tu usuario/organización y el nombre del repositorio:

| Uso | URL |
|-----|-----|
| **Lista M3U** | `https://USUARIO.github.io/REPO/lista_tivimate.m3u` |
| **EPG** | `https://USUARIO.github.io/REPO/epg_hispanohablante.xml.gz` |

### En TiviMate

1. **Ajustes → Listas de reproducción → Agregar → URL M3U** → pega la URL de la lista.
2. **Ajustes → Fuentes de EPG → Agregar** → pega la URL del EPG.
3. (Opcional, más cobertura) Agrega también EPG por país, por ejemplo:
   - España: `https://iptv-epg.org/files/epg-es.xml.gz`
   - México: `https://iptv-epg.org/files/epg-mx.xml.gz`
   - Chile: `https://iptv-epg.org/files/epg-cl.xml.gz`
   - Argentina: `https://iptv-epg.org/files/epg-ar.xml.gz`
4. Actualiza la lista y la guía.

> Nota: la EPG gratuita no cubre el 100% de canales públicos; es normal que algunos no tengan guía.

## Generar en local

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Salida en `dist/`:

- `lista_tivimate.m3u`
- `epg_hispanohablante.xml`
- `epg_hispanohablante.xml.gz`

## Publicar en GitHub

```bash
git init
git add .
git commit -m "Initial IPTV hispanohablante generator"
gh repo create iptv-hispanohablante --private --source=. --remote=origin --push
```

Luego en GitHub:

1. **Settings → Pages → Source: GitHub Actions**
2. Ejecuta el workflow **Build and Publish IPTV** (pestaña Actions), o haz push a `main`.

El workflow regenera la lista **cada día** y la publica en Pages.

## Fuentes

- Playlist: [iptv-org spa.m3u](https://iptv-org.github.io/iptv/languages/spa.m3u)
- EPG: [iptv-epg.org](https://iptv-epg.org/guides) (países de habla hispana)

Solo TV en vivo + EPG. Sin VOD.
