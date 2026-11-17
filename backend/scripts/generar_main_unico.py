"""Genera un main.py de UN SOLO ARCHIVO con todo el paquete bot/ (para desplegar como antes).

Uso:  python scripts/generar_main_unico.py   -> arma la carpeta despliegue/ (main.py + requirements.txt + Procfile + .python-version)
      Luego:  cd despliegue  y  gcloud run deploy sague-bot --source . --project sague-bot --region us-central1 --allow-unauthenticated

La fuente de verdad sigue siendo bot/: no edites el archivo generado; cambia bot/ y vuelve a generarlo.
"""
import ast
import os
import re
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Nombres repetidos entre módulos: se renombran dentro de su módulo (regex con \b, solo en ese archivo)
RENOMBRAR = {
    "bot.integraciones.tipo_cambio": {"_CACHE": "_CACHE_TIPO_CAMBIO"},
    "bot.datos.recursos": {"_CACHE": "_CACHE_RECURSOS"},
    "bot.rutas.webhook": {"bp": "bp_webhook"},
    "bot.rutas.cron": {"bp": "bp_cron"},
    "bot.rutas.diagnostico": {"bp": "bp_diagnostico"},
    "bot.rutas.salud": {"bp": "bp_salud"},
}
# Definiciones idénticas en dos módulos: se quita la copia del segundo
QUITAR_LINEAS = {"bot.conversacion.agenda_humana": ["FIN_DE_SEMANA = {5, 6}", "ENTRE_SEMANA = {0, 1, 2, 3, 4}"]}
APP = '''
# =====================================================================
# APLICACIÓN FLASK (antes bot/app.py)
# =====================================================================
def create_app():
    app = Flask(__name__)
    for blueprint in (bp_webhook, bp_cron, bp_diagnostico, bp_salud):
        app.register_blueprint(blueprint)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
'''


def modulos():
    out = {}
    for d, _, fs in os.walk(os.path.join(RAIZ, "bot")):
        if "__pycache__" in d:
            continue
        for f in sorted(fs):
            if f.endswith(".py") and f != "__init__.py":
                ruta = os.path.join(d, f)
                nombre = os.path.relpath(ruta, RAIZ)[:-3].replace(os.sep, ".")
                out[nombre] = ruta
    out.pop("bot.app", None)
    return out


def dependencias(fuente):
    deps = set()
    for n in ast.parse(fuente).body:
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("bot."):
            deps.add(n.module)
    return deps


def orden_topologico(mods, fuentes):
    orden, visitados = [], set()

    def visitar(m, pila=()):
        if m in visitados:
            return
        if m in pila:
            raise SystemExit(f"Import circular: {' -> '.join(pila + (m,))}")
        for d in sorted(dependencias(fuentes[m])):
            if d in mods:
                visitar(d, pila + (m,))
        visitados.add(m)
        orden.append(m)

    for m in sorted(mods, key=lambda x: (x != "bot.config", x)):
        visitar(m)
    return orden


def procesar(nombre, fuente, imports_externos):
    """Quita el docstring y los imports (los de bot/ se eliminan, los externos se suben arriba)."""
    arbol = ast.parse(fuente)
    lineas = fuente.splitlines()
    quitar = set()
    doc = ""
    for i, n in enumerate(arbol.body):
        if i == 0 and isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant) and isinstance(n.value.value, str):
            doc = n.value.value.strip().splitlines()[0]
            quitar.update(range(n.lineno - 1, n.end_lineno))
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            quitar.update(range(n.lineno - 1, n.end_lineno))
            if not (isinstance(n, ast.ImportFrom) and (n.module or "").startswith("bot")):
                texto = ast.get_source_segment(fuente, n)
                if texto not in imports_externos:
                    imports_externos.append(texto)
    cuerpo = "\n".join(l for i, l in enumerate(lineas) if i not in quitar)
    cuerpo = re.sub(r"^\s*from bot\.[\w.]+ import [\w, ]+\n", "", cuerpo, flags=re.M)  # imports perezosos dentro de funciones
    for viejo, nuevo in RENOMBRAR.get(nombre, {}).items():
        cuerpo = re.sub(rf"\b{viejo}\b", nuevo, cuerpo)
    for linea in QUITAR_LINEAS.get(nombre, []):
        cuerpo = cuerpo.replace(linea + "\n", "", 1)
    cuerpo = re.sub(r"\n{3,}", "\n\n\n", cuerpo).strip("\n")
    titulo = f"# {'=' * 69}\n# {nombre.replace('.', '/')}.py — {doc}\n# {'=' * 69}"
    return f"{titulo}\n{cuerpo}\n"


def unir_imports(lista):
    """'from datetime import datetime' + 'from datetime import timedelta' -> 'from datetime import datetime, timedelta'."""
    simples, desde = [], {}
    for texto in lista:
        n = ast.parse(texto).body[0]
        if isinstance(n, ast.ImportFrom):
            nombres = desde.setdefault(n.module, [])
            for a in n.names:
                item = f"{a.name} as {a.asname}" if a.asname else a.name
                if item not in nombres:
                    nombres.append(item)
        elif texto not in simples:
            simples.append(texto)
    return simples + [f"from {m} import {', '.join(sorted(ns))}" for m, ns in desde.items()]


def generar(salida):
    mods = modulos()
    fuentes = {m: open(r, encoding="utf-8").read() for m, r in mods.items()}
    imports_externos, bloques = [], []
    for m in orden_topologico(mods, fuentes):
        bloques.append(procesar(m, fuentes[m], imports_externos))
    if "import os" not in imports_externos:
        imports_externos.insert(0, "import os")
    if not any(re.match(r"from flask import .*\bFlask\b", i) for i in imports_externos):
        imports_externos.append("from flask import Flask")
    cabecera = (
        '"""Chatbot comercial SAGUE — versión de UN SOLO ARCHIVO para desplegar en Cloud Run (gunicorn main:app).\n\n'
        f"GENERADO AUTOMÁTICAMENTE desde bot/ el {datetime.now().strftime('%Y-%m-%d %H:%M')} con scripts/generar_main_unico.py.\n"
        'No lo edites a mano: cambia bot/ y vuelve a generarlo.\n"""\n'
    )
    imports_externos = unir_imports(imports_externos)
    estandar = sorted(i for i in imports_externos if i.split()[1].split(".")[0] in sys.stdlib_module_names)
    terceros = sorted(i for i in imports_externos if i not in estandar)
    texto = cabecera + "\n".join(estandar) + "\n\n" + "\n".join(terceros) + "\n\n\n" + "\n\n".join(bloques) + "\n" + APP
    os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
    with open(salida, "w", encoding="utf-8") as f:
        f.write(texto)
    ast.parse(texto)  # valida que sea Python correcto
    print(f"OK: {salida} ({texto.count(chr(10))} líneas, {len(mods)} módulos)")


PROCFILE = "web: gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app\n"
PYTHON_VERSION = "3.12\n"  # sin esto Cloud Run elige la última (3.14) y algunas librerías aún no la soportan


def armar_despliegue(carpeta):
    """Carpeta lista para 'gcloud run deploy --source .': nada más que lo necesario."""
    os.makedirs(carpeta, exist_ok=True)
    generar(os.path.join(carpeta, "main.py"))
    with open(os.path.join(RAIZ, "requirements.txt"), encoding="utf-8") as f:
        req = f.read()
    for nombre, contenido in (("requirements.txt", req), ("Procfile", PROCFILE), (".python-version", PYTHON_VERSION)):
        with open(os.path.join(carpeta, nombre), "w", encoding="utf-8", newline="\n") as f:
            f.write(contenido)
    print(f"Carpeta lista: {carpeta}  ->  cd {os.path.relpath(carpeta)} && gcloud run deploy sague-bot --source . "
          "--project sague-bot --region us-central1 --allow-unauthenticated")


if __name__ == "__main__":
    armar_despliegue(sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, "despliegue"))
