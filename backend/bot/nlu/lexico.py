"""Normalizador determinístico ES/EN (respaldo del NLU con IA y base de las pruebas). Usa bot/nlu/lexicon.json, el
mismo diccionario de jergas que el simulador del AI Sales Hub, así que la demo y el bot entienden lo mismo.
No llama a ninguna API: responde en ~1 ms."""
import json
import re
import unicodedata
from pathlib import Path

LEXICON = json.loads((Path(__file__).resolve().parent / "lexicon.json").read_text(encoding="utf-8"))


def sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").lower()


def _fmt(n):
    return f"{n:,}"


def detectar_idioma(texto, anterior=None):
    t = " " + re.sub(r"[^a-z0-9ñ' ]", " ", sin_tildes(texto)) + " "
    es = sum(1 for w in LEXICON["senales_idioma"]["es"] if f" {sin_tildes(w)} " in t)
    en = sum(1 for w in LEXICON["senales_idioma"]["en"] if f" {sin_tildes(w)} " in t)
    for tok in t.split():
        if tok in LEXICON["es"] and tok not in LEXICON["en"]:
            es += 0.6
        if tok in LEXICON["en"] and tok not in LEXICON["es"]:
            en += 0.6
    if re.search(r"[ñ¿¡]|ción\b", texto or ""):
        es += 1
    if es == en:
        return anterior or "es"
    return "es" if es > en else "en"


def extraer_presupuesto(crudo, jergas):
    t = sin_tildes(crudo)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(lucas|luca)\b", t)
    if m:
        n = round(float(m.group(1).replace(",", ".")) * 1000)
        jergas.append(f"{m.group(1)} {m.group(2)} ({_fmt(n)})")
        return n
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*k\b", t)
    if m:
        n = round(float(m.group(1).replace(",", ".")) * 1000)
        jergas.append(f"{m.group(1)}k ({_fmt(n)})")
        return n
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*mil\b", t)
    if m:
        return round(float(m.group(1).replace(",", ".")) * 1000)
    m = re.search(r"(?:\$|us\$|usd\s*|s/\s?)\s?(\d{1,3}(?:,\d{3})+|\d{3,})", t)
    if m:
        return int(m.group(1).replace(",", ""))
    m = re.search(r"\b(?:tengo|got|budget(?: is)?(?: like)?|presupuesto(?: de)?|cuento con)\s+(\d{3,})", t)
    return int(m.group(1)) if m else None


def extraer_hora(crudo, jergas):
    t = sin_tildes(crudo)
    m = re.search(r"(?:tipo|a las|como a las|round|around|at|@)\s*(\d{1,2})(?::(\d{2}))?\s*(y media|y cuarto|ish|pm|am|p\.m\.|de la tarde|de la noche)?", t) \
        or re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(pm|am|ish|y media)\b", t)
    if not m:
        return None
    h, minuto, suf = int(m.group(1)), int(m.group(2) or 0), m.group(3) or ""
    if suf == "y media":
        minuto = 30
    if suf == "y cuarto":
        minuto = 15
    if "ish" in suf:
        jergas.append(f"{m.group(1)}ish (≈ {h}:00)")
    if not suf.startswith("am"):
        if 1 <= h <= 7:
            h += 12
        elif re.search(r"pm|tarde|noche", suf) and h < 12:
            h += 12
    return None if h > 23 else f"{h:02d}:{minuto:02d}"


def fecha_relativa(t):
    for patron, valor in ((r"\b(manana|tomorrow)\b", "TOMORROW"), (r"\b(hoy|today|tonight|esta noche)\b", "TODAY"),
                          (r"\b(sabado|saturday)\b", "THIS_SATURDAY"), (r"\b(domingo|sunday)\b", "THIS_SUNDAY"),
                          (r"\b(lunes|monday)\b", "MONDAY")):
        if re.search(patron, t):
            return valor
    return None


def expandir(crudo, idioma, jergas):
    for de, a in (LEXICON.get("frases", {}).get(idioma) or {}).items():
        patron = re.compile(rf"\b{re.escape(de)}\b", re.I)
        if patron.search(crudo):
            crudo = patron.sub(a, crudo)
            if de not in ("q tal", "a cuanto sale"):
                jergas.append(f"{de} ({a})")
    dic = LEXICON[idioma]

    def reemplazar(m):
        tok = m.group(0)
        clave = sin_tildes(tok)
        if re.fullmatch(r"\d+k?", clave):
            return tok
        rep = dic.get(clave)
        if rep and sin_tildes(rep) != clave:
            jergas.append(f"{tok} ({rep})")
            return rep
        return rep or tok

    return re.sub(r"[A-Za-zÁÉÍÓÚáéíóúñÑ0-9'/]+", reemplazar, crudo)


INTENCIONES = [
    ("NOT_INTERESTED", r"\b(no me interesa|ya no|not interested|no thanks|stop)\b"),
    ("SLOT_SELECTION", r"^\s*(?:opcion |option |la |the )?(1|2|3|primera|segunda|tercera|first|second|third)(?: one| opcion| option)?\s*[.!]?\s*$"),
    ("RESCHEDULE", r"\b(reprogram|cambiar la (cita|hora)|reschedule|move (my|the) (appointment|tour))"),
    ("GREETING", r"^(hola|buenas|hey|hi|hello|buenos dias|buenas tardes)\b"),
    ("CASH_DISCOUNT", r"\b(contado|cash|al contado|pago unico|paid in full)\b"),
    ("PRICE_INQUIRY", r"\b(cuanto|precio|cuesta|sale|how much|price|pricing|cost|hm)\b"),
    ("OBJECTION_EXPENSIVE", r"\b(caro|carisimo|expensive|too much|pricey|out of my budget|muy alto)\b"),
    ("FINANCING_CALCULATION", r"\b(cuotas?|financ\w*|credito|inicial|payment plans?|monthly|down payment|down|installments?|plazos?)\b"),
    ("BUDGET_STATEMENT", r"\b(tengo|got|budget|presupuesto|cuento con|only have|solo tengo)\b"),
    ("INSURANCE_INQUIRY", r"\b(seguro|insurance|ppo|hmo|delta dental|cigna|metlife)\b"),
    ("SPECS_AND_PLANS", r"\b(planos?|floor ?plans?|pdf|ficha|brochure|specs?|guia|guide|sla|technical sheet|blueprints?)\b"),
    ("VIDEO_TOUR", r"\b(video|recorrido|walkthrough|tour video|demo video)\b"),
    ("LOCATION_INQUIRY", r"\b(donde|ubicacion|ubicados|direccion|where|located|location|address)\b"),
    ("SCHEDULE_REQUEST", r"\b(ver|visita|visitar|cita|agendar|tour|visit|appointment|book|call|reunion|puedo el|free this|se podra)\b"),
    ("COURTESY_WAIT", r"\b(lo pienso|te aviso|let me think|i'll let you know|despues te escribo)\b"),
]
_ORDEN_PRIMARIA = ["SCHEDULE_REQUEST", "OBJECTION_EXPENSIVE", "FINANCING_CALCULATION", "PRICE_INQUIRY"]
_SLOT = {"1": 1, "2": 2, "3": 3, "primera": 1, "segunda": 2, "tercera": 3, "first": 1, "second": 2, "third": 3}


def _item_mencionado(t, items):
    for it in items or []:
        for k in it.get("keywords") or []:
            if re.search(rf"\b{re.escape(sin_tildes(k)).replace('-', '[- ]?')}\b", t):
                return it, k
    return None, None


def normalizar(crudo, items=None, idioma_anterior=None):
    """Devuelve un dict con la forma de NormalizedTurn (ver bot/nlu_normalizer.py)."""
    idioma = detectar_idioma(crudo, idioma_anterior)
    jergas = []
    presupuesto = extraer_presupuesto(crudo, jergas)
    hora = extraer_hora(crudo, jergas)
    limpio = re.sub(r"\?{2,}", "?", re.sub(r"\s+", " ", expandir(crudo, idioma, jergas))).strip()
    limpio = re.sub(r"(\d+(?:[.,]\d+)?)\s*(lucas?|k)\b", lambda m: _fmt(round(float(m.group(1).replace(",", ".")) * 1000)), limpio, flags=re.I)
    limpio = limpio[:1].upper() + limpio[1:]
    t = sin_tildes(limpio) + " " + sin_tildes(crudo)
    solo = sin_tildes(crudo).strip()

    intents = [n for n, p in INTENCIONES if re.search(p, solo if n in ("SLOT_SELECTION", "GREETING") else t)]
    if presupuesto and "BUDGET_STATEMENT" not in intents:
        intents.append("BUDGET_STATEMENT")
    intents = intents or ["GENERAL_INFO"]

    ent = {}
    item, clave = _item_mencionado(t, items)
    if item:
        ent.update(service_keyword=clave, catalog_item_id=str(item.get("id")))
    if "CASH_DISCOUNT" in intents:
        ent["payment_type"] = "CASH"
    elif "FINANCING_CALCULATION" in intents:
        ent["payment_type"] = "FINANCING"
    if "INSURANCE_INQUIRY" in intents:
        m = re.search(r"delta dental|cigna|metlife|ppo|hmo", t)
        ent["insurance"] = m.group(0) if m else ("seguro" if idioma == "es" else "insurance")
    if presupuesto:
        ent.update(budget_amount=presupuesto, budget_currency="LOCAL_OR_UNSPECIFIED")
    if "OBJECTION_EXPENSIVE" in intents:
        ent["price_objection"] = True
    rel = fecha_relativa(t)
    if rel:
        ent["proposed_date_relative"] = rel
    if hora:
        ent["proposed_time"] = hora
    if re.search(r"saliendo de(l)? (la chamba|trabajo|trabajar)|after work|despues del trabajo|salgo del trabajo", t):
        h, mi = map(int, (hora or "18:00").split(":"))
        fin = h * 60 + mi - 30
        ent["work_end_constraint"] = f"{fin // 60:02d}:{fin % 60:02d}"
    m = re.search(r"\bafter (\d{1,2})\b|\bdespues de las (\d{1,2})\b", t)
    if m and "work_end_constraint" not in ent:
        h = int(m.group(1) or m.group(2))
        ent["work_end_constraint"] = f"{h + 12 if h < 8 else h}:00"
    m = re.match(r"^(?:opcion |option |la |the )?(1|2|3|primera|segunda|tercera|first|second|third)", solo)
    if "SLOT_SELECTION" in intents and m:
        ent["selected_slot_index"] = _SLOT[m.group(1)]

    if "SCHEDULE_REQUEST" in intents and "OBJECTION_EXPENSIVE" in intents:
        primaria = "SCHEDULE_AND_PRICE_OBJECTION"
    elif "FINANCING_CALCULATION" in intents and "SCHEDULE_REQUEST" in intents:
        primaria = "FINANCING_AND_SCHEDULE"
    else:
        primaria = next((o for o in _ORDEN_PRIMARIA if o in intents), intents[0])
    return {
        "detected_language": idioma,
        "regional_slang_detected": list(dict.fromkeys(jergas)),
        "clean_text": limpio,
        "primary_intent": primaria,
        "intents": [primaria] + [i for i in intents if i != primaria],
        "entities": ent,
        "source": "lexicon",
    }
