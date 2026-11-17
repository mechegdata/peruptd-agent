"""Detección y resumen de la modalidad de compra (contado / crédito / inicial)."""
import re

from bot.config import PLAZO_REFERENCIAL_ANIOS, PRECIO_LISTA_USD, TASA_REFERENCIAL_TEA
from bot.nlp.patrones import AFIRMA_RE, NEG_CLAUSULA_RE, NIEGA_RE
from bot.utils.texto import limpiar_texto


def detectar_financiamiento(texto):
    """Lee por cláusulas para entender cosas como 'no tengo crédito aprobado pero sí tengo inicial'."""
    t = limpiar_texto(texto)
    out = {"modalidad": None, "inicial": None, "credito_aprobado": None}
    nada = bool(re.search(r"\b(ni nada|no tengo nada|nada todavia|todavia nada|aun nada|nada aun)\b", t))
    for c in re.split(r"\bpero\b|\baunque\b|,|;|\.|\by\b|\bo sea\b", t):
        c = c.strip()
        if not c:
            continue
        neg = bool(NEG_CLAUSULA_RE.search(c))
        # "¿Cuánto sería una inicial adecuada?" pregunta, no afirma que la tenga
        es_pregunta_c = bool(re.search(r"\b(cuant\w*|como|cual\w*|que|donde|requisitos?)\b", c)) and not re.search(
            r"\b(tengo|tenemos|cuento|contamos|dispongo|disponemos|junte|juntamos|ahorre|ahorramos|aprobaron)\b", c)
        if re.search(r"\b(al contado|contado|efectivo|cash|fondos propios|sin credito|sin banco)\b", c) and not re.search(r"\bno\b.*contado", c):
            if not es_pregunta_c:
                out["modalidad"] = "contado"
            continue
        if es_pregunta_c:
            if re.search(r"\b(credito|hipotecari\w*|banco|prestamo|financiamiento)\b", c) and not neg:
                out["modalidad"] = out["modalidad"] or "credito"
            continue
        if re.search(r"\binicial\b|\b(10|20) ?%|\b(10|20) por ciento|ahorrad|mis ahorros", c):
            out["inicial"] = not neg
        if re.search(r"pre ?aprobad|aprobad|aprobaron|calific", c):
            out["credito_aprobado"] = not neg
            out["modalidad"] = out["modalidad"] or "credito"
        elif re.search(r"\b(credito|hipotecari\w*|banco|prestamo|financiamiento|financiad\w*|mivivienda|techo propio)\b", c) and not neg:
            out["modalidad"] = out["modalidad"] or "credito"
    if nada:
        out["inicial"] = False if out["inicial"] is None else out["inicial"]
        out["credito_aprobado"] = False if out["credito_aprobado"] is None else out["credito_aprobado"]
    return out


def estado_financiero(meta):
    """True = calificado (contado / inicial / crédito aprobado), False = sin inicial ni crédito, None = no sabemos."""
    if meta.get("fin_modalidad") == "contado":
        return True
    if meta.get("fin_inicial") is True or meta.get("fin_credito_aprobado") is True:
        return True
    if meta.get("fin_inicial") is False and meta.get("fin_credito_aprobado") is not True:
        return False
    fp = meta.get("forma_pago")
    if fp and fp not in ["Por consultar", "Contado / Crédito Hipotecario"]:
        d = detectar_financiamiento(fp)
        if d["modalidad"] == "contado" or d["inicial"] is True or d["credito_aprobado"] is True:
            return True
        if d["inicial"] is False:
            return False
    return None


def resumen_financiero(meta):
    calif = estado_financiero(meta)
    if meta.get("fin_modalidad") == "contado":
        return "Contado"
    partes = []
    if meta.get("fin_modalidad") == "credito":
        partes.append("Crédito hipotecario")
    if meta.get("fin_inicial") is True:
        partes.append("con inicial")
    if meta.get("fin_inicial") is False:
        partes.append("SIN inicial (ofrecer asesor hipotecario)")
    if meta.get("fin_credito_aprobado") is True:
        partes.append("crédito preaprobado")
    if meta.get("fin_credito_aprobado") is False:
        partes.append("sin crédito aprobado aún")
    if not partes:
        return meta.get("forma_pago") or ("Por validar" if calif is None else "")
    return ", ".join(partes)


def pregunta_por_financiamiento(texto):
    """True si alguna pregunta (¿...?) del texto le consulta al cliente por su inicial / crédito / contado."""
    return any(re.search(r"(?i)inicial|preaprobado|contado o", q) for q in re.findall(r"¿[^?¿]*\?", texto or ""))


def quitar_preguntas_financiamiento(texto):
    t = re.sub(r"¿[^?¿]*(?:inicial|preaprobado|contado o)[^?¿]*\?\s*(?:😊)?", "", texto or "")
    t = re.sub(r"(?i)\b(cuéntame|coméntame)[,:]?\s*$", "", t.strip())
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def inferir_estado_de_historial(meta, mensajes_db):
    """Reconstruye lo que el cliente YA dijo sobre cómo pagará (contado / crédito / inicial) leyendo todo el historial,
    incluidas respuestas cortas ("no todavía") a preguntas del bot o del asesor humano. Solo completa lo que falte."""
    visto = {}
    prev_bot = ""
    for m in mensajes_db or []:
        txt = m.get("contenido") or ""
        if m.get("rol") != "user":
            prev_bot = txt
            continue
        d = detectar_financiamiento(txt)
        tl = limpiar_texto(txt)
        if all(v is None for v in d.values()) and pregunta_por_financiamiento(prev_bot) and len(tl) <= 60:
            if NIEGA_RE.match(tl):
                d = {"modalidad": None, "inicial": False, "credito_aprobado": False}
            elif AFIRMA_RE.match(tl):
                d = {"modalidad": None, "inicial": True, "credito_aprobado": None}
        for k_src, k_meta in (("modalidad", "fin_modalidad"), ("inicial", "fin_inicial"), ("credito_aprobado", "fin_credito_aprobado")):
            if d[k_src] is not None:
                visto[k_meta] = d[k_src]
        if pregunta_por_financiamiento(prev_bot):
            visto["_preguntado"] = True
    for k, v in visto.items():
        if k == "_preguntado":
            if not meta.get("veces_pregunta_fin"):
                meta["veces_pregunta_fin"] = 1
        elif meta.get(k) is None:
            meta[k] = v


def cuota_referencial(porc_inicial):
    prestamo = PRECIO_LISTA_USD * (1 - porc_inicial)
    r = (1 + TASA_REFERENCIAL_TEA / 100) ** (1 / 12) - 1
    n = PLAZO_REFERENCIAL_ANIOS * 12
    return prestamo * r / (1 - (1 + r) ** -n)
