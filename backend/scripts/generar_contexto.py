#!/usr/bin/env python3
"""Genera la documentación automática del proyecto a partir del código.

Salidas (NO editar a mano, se sobrescriben):
  - docs/CONTEXTO_AUTO.md  -> mapa de módulos, funciones, rutas, tablas, estado del lead, variables y deuda técnica
  - .env.example           -> todas las variables de entorno que lee el código (secretos vacíos)

Uso:
  python scripts/generar_contexto.py           # regenera
  python scripts/generar_contexto.py --check   # falla (exit 1) si los archivos no están al día (CI)

Se ejecuta solo: en el hook pre-commit de git, en el hook de Claude Code (.claude/settings.json)
y en GitHub Actions. Solo usa la librería estándar.
"""
import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PAQUETE = RAIZ / "bot"
SALIDA_MD = RAIZ / "docs" / "CONTEXTO_AUTO.md"
SALIDA_ENV = RAIZ / ".env.example"

# Límites de buenas prácticas (ver docs/CONVENCIONES.md)
MAX_LINEAS_ARCHIVO = 300
MAX_LINEAS_FUNCION = 60
PALABRAS_SECRETAS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "PASS")


def modulos():
    archivos = sorted(PAQUETE.rglob("*.py"))
    for f in [RAIZ / "main.py"] + archivos:
        if f.exists() and f.name != "__init__.py":
            yield f


def nombre_modulo(f):
    rel = f.relative_to(RAIZ).with_suffix("")
    return ".".join(rel.parts)


def primera_linea(doc):
    return (doc or "").strip().split("\n")[0].strip()


def analizar(f):
    src = f.read_text(encoding="utf-8")
    tree = ast.parse(src)
    info = {
        "modulo": nombre_modulo(f),
        "ruta": f.relative_to(RAIZ).as_posix(),
        "lineas": len(src.splitlines()),
        "doc": primera_linea(ast.get_docstring(tree)),
        "funciones": [],
        "rutas": [],
        "env": [],
        "tablas": set(),
        "claves_lead": set(),
        "claves_respuesta": set(),
        "importa": set(),
    }
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            largo = n.end_lineno - (min([d.lineno for d in n.decorator_list] or [n.lineno])) + 1
            info["funciones"].append((n.name, largo, primera_linea(ast.get_docstring(n))))
            for d in n.decorator_list:
                if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "route" and d.args:
                    metodos = []
                    for kw in d.keywords:
                        if kw.arg == "methods" and isinstance(kw.value, ast.List):
                            metodos = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
                    info["rutas"].append((d.args[0].value, ",".join(metodos) or "GET", n.name))
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("bot"):
            info["importa"].add(n.module)
    for n in ast.walk(tree):
        # os.environ.get("X", "default")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get" \
                and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == "environ" and n.args \
                and isinstance(n.args[0], ast.Constant):
            defecto = ""
            if len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                defecto = str(n.args[1].value)
            info["env"].append((n.args[0].value, defecto))
        # supabase.table("x")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "table" \
                and n.args and isinstance(n.args[0], ast.Constant):
            info["tablas"].add(n.args[0].value)
        # claves del estado del lead (variables meta*) y de la respuesta (parsed*)
        for destino, prefijo in (("claves_lead", "meta"), ("claves_respuesta", "parsed")):
            if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id.startswith(prefijo) \
                    and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
                info[destino].add(n.slice.value)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
                    and n.func.value.id.startswith(prefijo):
                if n.func.attr == "get" and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    info[destino].add(n.args[0].value)
                if n.func.attr == "update" and n.args and isinstance(n.args[0], ast.Dict):
                    info[destino].update(k.value for k in n.args[0].keys if isinstance(k, ast.Constant))
    return info


def es_secreto(nombre):
    return any(p in nombre.upper() for p in PALABRAS_SECRETAS)


def generar():
    datos = [analizar(f) for f in modulos()]
    total = sum(d["lineas"] for d in datos)
    out = []
    w = out.append
    w("# Contexto automático del código")
    w("")
    w("> ⚠️ Archivo GENERADO por `scripts/generar_contexto.py`. No lo edites a mano: se sobrescribe en cada commit.")
    w("> Para contexto humano (decisiones, negocio, arquitectura) ver `CLAUDE.md` y `docs/`.")
    w("")
    w(f"**Módulos:** {len(datos)} · **Líneas totales:** {total} · "
      f"**Límites:** archivo ≤ {MAX_LINEAS_ARCHIVO} líneas, función ≤ {MAX_LINEAS_FUNCION} líneas")
    w("")

    w("## 1. Mapa de módulos")
    w("")
    w("| Módulo | Líneas | Responsabilidad |")
    w("|---|---:|---|")
    for d in datos:
        alerta = " ⚠️" if d["lineas"] > MAX_LINEAS_ARCHIVO else ""
        w(f"| `{d['ruta']}` | {d['lineas']}{alerta} | {d['doc'] or '—'} |")
    w("")

    w("## 2. Rutas HTTP")
    w("")
    w("| Ruta | Métodos | Función | Archivo |")
    w("|---|---|---|---|")
    for d in datos:
        for ruta, met, fn in d["rutas"]:
            w(f"| `{ruta}` | {met} | `{fn}` | `{d['ruta']}` |")
    w("")

    w("## 3. Funciones por módulo")
    w("")
    for d in datos:
        if not d["funciones"]:
            continue
        w(f"### `{d['modulo']}`")
        if d["importa"]:
            w(f"_Depende de:_ {', '.join(f'`{m}`' for m in sorted(d['importa']))}")
        w("")
        for nombre, largo, doc in d["funciones"]:
            alerta = " ⚠️" if largo > MAX_LINEAS_FUNCION else ""
            w(f"- `{nombre}()` ({largo} líneas{alerta}){' — ' + doc if doc else ''}")
        w("")

    w("## 4. Tablas de Supabase usadas")
    w("")
    tablas = {}
    for d in datos:
        for t in d["tablas"]:
            tablas.setdefault(t, []).append(d["ruta"])
    for t in sorted(tablas):
        w(f"- **`{t}`** ← {', '.join(f'`{r}`' for r in sorted(tablas[t]))}")
    w("")

    w("## 5. Estado del lead (`leads.interes`, JSON)")
    w("")
    w("Claves que el código lee o escribe en el diccionario de estado del lead (variables `meta*`):")
    w("")
    claves = sorted(set().union(*[d["claves_lead"] for d in datos]))
    w(", ".join(f"`{c}`" for c in claves) or "—")
    w("")
    w("## 6. Contrato de respuesta de los motores (`parsed`)")
    w("")
    w("Claves del diccionario que devuelven los motores de respuesta / Gemini:")
    w("")
    claves_r = sorted(set().union(*[d["claves_respuesta"] for d in datos]))
    w(", ".join(f"`{c}`" for c in claves_r) or "—")
    w("")

    w("## 7. Variables de entorno")
    w("")
    w("| Variable | Valor por defecto en código | Archivo |")
    w("|---|---|---|")
    vistos = {}
    for d in datos:
        for nombre, defecto in d["env"]:
            if nombre not in vistos:
                vistos[nombre] = (defecto, d["ruta"])
    for nombre in sorted(vistos):
        defecto, ruta = vistos[nombre]
        mostrado = "(secreto)" if es_secreto(nombre) and defecto else (defecto[:60] + ("…" if len(defecto) > 60 else ""))
        mostrado = mostrado.replace("|", "\\|").replace("\n", " ")
        w(f"| `{nombre}` | {mostrado or '—'} | `{ruta}` |")
    w("")

    w("## 8. Deuda técnica detectada automáticamente")
    w("")
    deuda = []
    for d in datos:
        if d["lineas"] > MAX_LINEAS_ARCHIVO:
            deuda.append(f"- Archivo `{d['ruta']}` tiene {d['lineas']} líneas (> {MAX_LINEAS_ARCHIVO}). Dividir por responsabilidad.")
        for nombre, largo, _ in d["funciones"]:
            if largo > MAX_LINEAS_FUNCION:
                deuda.append(f"- Función `{d['modulo']}.{nombre}()` tiene {largo} líneas (> {MAX_LINEAS_FUNCION}).")
        if not d["doc"]:
            deuda.append(f"- `{d['ruta']}` no tiene docstring de módulo.")
    w("\n".join(deuda) if deuda else "Sin alertas. 🎉")
    w("")
    md = "\n".join(out)

    env = ["# GENERADO por scripts/generar_contexto.py — copia a .env y completa. NUNCA subas .env a git.",
           "# Secretos (TOKEN/KEY/SECRET) van vacíos: en producción usa Google Secret Manager.", ""]
    for nombre in sorted(vistos):
        defecto = vistos[nombre][0]
        valor = "" if es_secreto(nombre) else defecto.replace("\n", " ")
        env.append(f"{nombre}={valor}")
    return md, "\n".join(env) + "\n"


def main():
    md, env = generar()
    check = "--check" in sys.argv
    cambios = []
    for ruta, contenido in ((SALIDA_MD, md), (SALIDA_ENV, env)):
        actual = ruta.read_text(encoding="utf-8") if ruta.exists() else None
        if actual != contenido:
            cambios.append(ruta.relative_to(RAIZ).as_posix())
            if not check:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_text(contenido, encoding="utf-8", newline="\n")
    if check and cambios:
        print("Documentación desactualizada:", ", ".join(cambios))
        print("Ejecuta: python scripts/generar_contexto.py")
        sys.exit(1)
    if cambios and "--silencioso" not in sys.argv:
        print("Actualizado:", ", ".join(cambios))


if __name__ == "__main__":
    main()
