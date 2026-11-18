"""Arma hub/dist/index.html (una sola página, sin dependencias) a partir de hub/src y shared/lexicon.json."""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
src = RAIZ / "src"
html = (src / "index.html").read_text(encoding="utf-8")
lexicon = json.loads((RAIZ.parent / "backend" / "bot" / "nlu" / "lexicon.json").read_text(encoding="utf-8"))
scripts = "\n".join((src / f).read_text(encoding="utf-8") for f in ("data.js", "nlu.js", "engines.js", "app.js", "live.js", "crm.js"))
html = html.replace("/*@@STYLE@@*/", (src / "style.css").read_text(encoding="utf-8"))
html = html.replace("/*@@LEXICON@@*/", json.dumps(lexicon, ensure_ascii=False))
html = html.replace("/*@@SCRIPTS@@*/", scripts.replace("</script", "<\\/script"))
(RAIZ / "dist").mkdir(exist_ok=True)
(RAIZ / "dist" / "index.html").write_text(html, encoding="utf-8")
estatico = RAIZ.parent / "backend" / "bot" / "static"          # el backend lo sirve en GET /app (CRM con login; ?demo=1 = demo) y /hub (demo + modo en vivo)
estatico.mkdir(exist_ok=True)
(estatico / "hub.html").write_text(html, encoding="utf-8")
print("dist/index.html", len(html), "bytes")
