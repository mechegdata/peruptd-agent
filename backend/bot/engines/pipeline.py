"""Fila de motores (Capa 2) + redactor bilingüe (Capa 3) para tenants en modo 'catalogo'.
run() es puro: recibe el turno normalizado, el estado del lead y el catálogo, y devuelve un ResultadoTurno con el texto,
la multimedia, las alertas y los cambios de estado. El envío, el calendario y el CRM los hace bot/agente.py."""
from dataclasses import dataclass, field
from datetime import datetime

from bot.engines import agenda, finanzas, multimedia, objeciones
from bot.engines.textos import L, campo, dinero, nombre


@dataclass
class ResultadoTurno:
    texto: str
    media: list = field(default_factory=list)
    alertas: list = field(default_factory=list)          # [(texto, urgente)]
    traza: list = field(default_factory=list)            # [(motor, detalle)] -> "AI Brain X-Ray" y registros
    cambios: dict = field(default_factory=dict)          # estado del lead a guardar
    slots: list = field(default_factory=list)            # horarios ofrecidos (datetime)
    reservar: object = None                              # datetime elegido por el cliente -> crear evento


def _item(catalogo, ent, estado):
    buscado = ent.get("catalog_item_id") or estado.get("interested_catalog_item_id")
    return next((i for i in catalogo if str(i.get("id")) == str(buscado)), catalogo[0] if catalogo else None)


def run(turno, estado, catalogo, tenant, buscar_libres=None, ahora=None):
    ahora = ahora or datetime.now()
    idioma = turno.detected_language
    ent = turno.entities.model_dump()
    item = _item(catalogo, ent, estado)
    if not item:
        return ResultadoTurno(L(idioma, "Thanks for writing! An advisor will reply in a few minutes 🙌", "¡Gracias por escribirnos! En unos minutos te responde un asesor 🙌"),
                              alertas=[("Catálogo vacío: revisar la sincronización con el CRM", True)])
    r = ResultadoTurno(texto="", cambios={"interested_catalog_item_id": str(item["id"]), "preferred_language": idioma})
    partes, triggers = [], []
    mon = item.get("currency") or "USD"
    asesor = tenant.get("advisor_name") or L(idioma, "our sales lead", "nuestro asesor principal")

    if turno.tiene("NOT_INTERESTED"):
        r.cambios["stage"] = "lost"
        r.traza.append(("Cortesía", "cierra con cortesía y detiene el seguimiento"))
        r.texto = L(idioma, "No problem at all, thanks for your time! If anything changes, I'm here 🙌", "¡Sin problema, gracias por tu tiempo! Si algo cambia, aquí estoy 🙌")
        return r

    ofrecidos = estado.get("offered_slots") or []
    if turno.tiene("SLOT_SELECTION") and ent.get("selected_slot_index") and len(ofrecidos) >= ent["selected_slot_index"]:
        r.reservar = datetime.fromisoformat(ofrecidos[ent["selected_slot_index"] - 1])
        r.traza.append(("Agenda", f"opción {ent['selected_slot_index']} → {r.reservar.isoformat()}"))
        r.cambios.update(offered_slots=[], stage="booked")
        triggers.append("LOCATION_FACADE")
        r.texto = ""  # el texto de confirmación lo pone agente.py cuando el calendario confirma
        r.media = multimedia.elegir(item, triggers, estado.get("sent_media_ids"))
        return r

    saludo = "" if estado.get("greeted") else L(idioma, f"Hi! I'm {tenant.get('bot_name', 'Ava')} from {tenant.get('name', '')} 👋 ", f"¡Hola! Soy {tenant.get('bot_name', 'Ava')} de {tenant.get('name', '')} 👋 ")
    if saludo or turno.tiene("GREETING", "PRICE", "CASH", "GENERAL_INFO"):
        specs = item.get("specs_json") or {}
        specs = specs.get(idioma) or specs.get("es") or {}
        detalle = " · ".join(f"{k}: {v}" for k, v in list(specs.items())[:4])
        precio = ""
        if turno.tiene("CASH"):
            precio = L(idioma, f" Cash price: {dinero(item.get('cash_price') or item['list_price'], idioma, mon)} (list {dinero(item['list_price'], idioma, mon)}).",
                       f" Al contado: {dinero(item.get('cash_price') or item['list_price'], idioma, mon)} (precio de lista {dinero(item['list_price'], idioma, mon)}).")
        elif turno.tiene("PRICE"):
            precio = L(idioma, f" It's {dinero(item['list_price'], idioma, mon)}, or {dinero(item.get('cash_price') or item['list_price'], idioma, mon)} paying cash.",
                       f" Cuesta {dinero(item['list_price'], idioma, mon)}, o {dinero(item.get('cash_price') or item['list_price'], idioma, mon)} al contado.")
        partes.append(f"{saludo}*{nombre(item, idioma)}* — {detalle}.{precio}")
        r.traza.append(("Catálogo", f"{item.get('external_crm_id') or item['id']} · lista {item['list_price']} · contado {item.get('cash_price')}"))
        r.cambios["greeted"] = True
        if not estado.get("sent_media_ids"):
            triggers.append("FIRST_INFO")

    if ent.get("price_objection"):
        nivel = min(3, int(estado.get("price_objection_count") or 0) + 1)
        o = objeciones.responder(item, nivel, idioma, asesor)
        partes.append(o["texto"])
        if o["trigger"]:
            triggers.insert(0, o["trigger"])
        r.alertas.append((o["alerta"], o["urgente"]))
        r.traza.append((f"Objeción {nivel}/3", o["alerta"]))
        r.cambios["price_objection_count"] = nivel

    if ent.get("budget_amount") is not None or ent.get("payment_type") == "FINANCING":
        f = finanzas.evaluar(item, ent.get("budget_amount"), ent.get("payment_type"), idioma)
        if f:
            partes.append(f["texto"])
            r.traza.append(("Presupuesto", f"{f['regla']} {f['calculo']}"))
    if ent.get("budget_amount") is not None:
        r.cambios["stated_budget"] = ent["budget_amount"]
    if ent.get("payment_type"):
        r.cambios["payment_method"] = ent["payment_type"]
    if ent.get("insurance") and campo(item, "insurance", idioma):
        partes.append(campo(item, "insurance", idioma) + ".")
        r.traza.append(("Seguro", ent["insurance"]))

    if turno.tiene("SPECS_AND_PLANS"):
        triggers.append("SPECS_PDF")
        partes.append(L(idioma, "Sending you the document 👇", "Te envío el documento 👇"))
    if turno.tiene("VIDEO_TOUR"):
        triggers.append("VIDEO_TOUR")
        partes.append(L(idioma, "Here's the video 🎬", "Aquí tienes el video 🎬"))
    if turno.tiene("LOCATION"):
        triggers.append("LOCATION_FACADE")
        partes.append(f"📍 {item.get('location_address') or tenant.get('address', '')} — {item.get('google_maps_url') or ''}".rstrip(" —"))

    if turno.tiene("SCHEDULE") and buscar_libres:
        r.slots = agenda.proponer(ent, buscar_libres, ahora)
        partes.append(agenda.texto_opciones(r.slots, ent, idioma, ahora.date()))
        r.cambios["offered_slots"] = [s.isoformat() for s in r.slots]
        r.traza.append(("Agenda", f"{len(r.slots)} horarios libres desde {ent.get('work_end_hour') or 'apertura'}"))

    etapa = estado.get("stage") or "new"
    if etapa == "new" and (r.cambios.get("payment_method") or r.cambios.get("stated_budget") or r.slots):
        r.cambios["stage"] = "qualified"
    if not partes:
        partes.append(L(idioma, f"Happy to help! {campo(item, 'promo_bonus', 'en')} Want the details or shall we book a visit?",
                        f"¡Con gusto! {campo(item, 'promo_bonus', 'es')} ¿Te envío los detalles o agendamos una visita?"))
        r.traza.append(("Respaldo", "sin motor aplicable: respuesta corta con datos del catálogo"))

    r.media = multimedia.elegir(item, triggers, estado.get("sent_media_ids"))
    if r.media:
        r.traza.append(("Multimedia", " + ".join(f"{m['trigger_moment']}:{m['id']}" for m in r.media)))
    r.texto = "\n\n".join(p for p in partes if p)
    return r
