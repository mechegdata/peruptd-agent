"""Agenda 'humana': entiende restricciones y preferencias ('trabajo hasta las 5', 'fin de semana', 'a eso de las 4.30').

Aprendido de chats reales (Eloisa): quien trabaja hasta las 5 prefiere fin de semana o venir saliendo del trabajo
(el asesor recibe hasta las 7-8 p. m.); una hora suelta después de ofrecer un día ('a eso de las 4.30') es para ESE día.
"""
import re
from datetime import datetime, timedelta

from bot.config import DURACION_VISITA_MIN, HORA_FIN_VISITAS, HORA_INICIO_NOCHE, HORARIO_NOCHE_HASTA_TXT, LIMA_TZ
from bot.conversacion.base import _resp
from bot.conversacion.slots import elegir_slot_ofrecido, horarios_en
from bot.integraciones.calendario import fecha_apertura_txt, get_free_slots, primer_dia_visitas, verificar_slot
from bot.nlp.restricciones import cumple_restriccion, detectar_restriccion_horaria
from bot.nlp.dias import TODOS, describir_dias
from bot.utils.fechas import DIAS_ES, a_las, format_hora_es
from bot.utils.texto import limpiar_texto

FIN_DE_SEMANA = {5, 6}
ENTRE_SEMANA = {0, 1, 2, 3, 4}
PIE_FIN = ("Y para registrarte con el ingeniero: ¿la compra la evalúas al contado o con crédito hipotecario "
           "(el banco pide desde el 10% de inicial)?")


def slots_vigentes(meta, etapas=("ofrecio_horarios",)):
    """Horarios ya ofrecidos que siguen en el futuro (para no cambiarle la lista al cliente)."""
    if meta.get("etapa") not in etapas:
        return []
    limite = datetime.now(LIMA_TZ) + timedelta(hours=1)
    vigentes = []
    for iso in meta.get("slots_ofrecidos") or []:
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError:
            continue
        if dt > limite:
            vigentes.append(dt)
    return vigentes


def _pie(meta, pide_fin, extra=""):
    partes = [extra] if extra else []
    if pide_fin:
        meta["pregunta_fin_pendiente"] = True
        partes.append(PIE_FIN)
    return "\n\n".join(partes)


def _fin_de_semana(n=3):
    """Los horarios libres más próximos del fin de semana, según el calendario."""
    return get_free_slots(n=n, dias_semana=FIN_DE_SEMANA)


def _hora_txt(h):
    return f"{h % 12 or 12} {'a. m.' if h < 12 else 'p. m.'}"


def _por_trabajo(restr, pref_dias, meta, ofrecer, coma, pide_fin):
    """'Trabajo hasta las 5' / 'de lunes a viernes trabajo' / 'en la noche': como el asesor —
    entre semana lo recibe saliendo del trabajo (hasta las 8 o 9 p. m.) y el fin de semana, claro que sí, con horarios del calendario."""
    desde = restr.get("desde") if restr["tipo"] == "trabajo" and restr.get("desde") else HORA_INICIO_NOCHE
    desde = max(desde, HORA_INICIO_NOCHE) if restr["tipo"] == "noche" else desde
    meta["ventana_noche_desde"] = desde
    ventana = f"desde las {_hora_txt(desde)} {HORARIO_NOCHE_HASTA_TXT}"
    finde = _fin_de_semana(3)
    if pref_dias == FIN_DE_SEMANA:
        enc = f"¡Claro que sí{coma}! 😊 El fin de semana te recibimos con todo gusto. Estos son los horarios más próximos:"
        extra = f"Y si algún día entre semana se te hace más fácil, también te puedo recibir saliendo del trabajo, {ventana} 😉"
        return ofrecer(finde, enc, _pie(meta, pide_fin, extra))
    salida = "en la noche" if restr["tipo"] == "noche" else "saliendo del trabajo"
    enc = (f"¡Claro que sí{coma}! 😊 Mira, entre semana te puedo recibir {salida}, {ventana}, sin correteos: "
           "solo dime qué día y a qué hora te acomoda. Y el fin de semana, claro que sí; estos son los horarios más próximos:")
    return ofrecer(finde, enc, _pie(meta, pide_fin))


def _encabezado_general(restr, coma):
    if restr["tipo"] == "almuerzo":
        return f"¡Claro que sí{coma}! 😊 Para tu hora de almuerzo tengo libre:"
    if restr.get("hasta") is not None:
        return f"¡Claro que sí{coma}! 😊 Te busqué horarios antes de las {restr['hora_txt']}:"
    return f"¡Claro que sí{coma}! 😊 Te busqué horarios desde las {restr['hora_txt']}:"


def _con_restriccion(restr, user_text, fh, pref_dias, meta, ofrecer, coma, pide_fin):
    if restr.get("hora_raw") is not None and fh.get("hora") == restr["hora_raw"]:
        fh["hora"], fh["minuto"] = None, 0
    elif fh.get("hora") is not None:
        return None  # además propuso una hora concreta distinta ('el sábado a las 10, trabajo hasta las 5')
    if meta.get("etapa") == "ofrecio_horarios" and elegir_slot_ofrecido(limpiar_texto(user_text), meta.get("slots_ofrecidos") or [], fh):
        return None  # eligió una opción ('la 2, porque trabajo hasta las 5')
    meta["restriccion_horaria"] = {k: restr[k] for k in ["tipo", "desde", "hasta"]}
    sale_tarde = restr["tipo"] == "noche" or (restr["tipo"] == "trabajo" and (restr.get("desde") is None or restr["desde"] >= HORA_FIN_VISITAS - 1))
    if sale_tarde and not fh.get("fecha"):
        return _por_trabajo(restr, pref_dias, meta, ofrecer, coma, pide_fin)
    filtro = lambda dt: cumple_restriccion(dt, restr, DURACION_VISITA_MIN)  # noqa: E731
    if fh.get("fecha"):
        slots = get_free_slots(n=3, dia=fh["fecha"], turno=fh.get("turno"), filtro=filtro)
    else:
        slots = get_free_slots(n=3, dias_semana=pref_dias, filtro=filtro)
    if not slots:
        return _por_trabajo(restr, pref_dias, meta, ofrecer, coma, pide_fin)
    return ofrecer(slots, _encabezado_general(restr, coma), _pie(meta, pide_fin))


def agenda_por_preferencias(user_text, fh, pref_dias, meta, ofrecer, coma, pide_fin=False, rechaza=False):
    """Respuesta con horarios que respetan lo que dijo el cliente, o None para seguir el flujo normal.
    OJO: si la hora del mensaje es la de la restricción, se borra de 'fh' para que nadie la tome como cita."""
    restr = detectar_restriccion_horaria(user_text)
    if restr:
        return _con_restriccion(restr, user_text, fh, pref_dias, meta, ofrecer, coma, pide_fin)
    if pref_dias and fh.get("hora") is not None and fh.get("fecha") is None:
        h, mi = fh["hora"], fh.get("minuto") or 0
        slots = horarios_en(pref_dias, [(h, mi)], n=2, por_dia=1)
        cuando = "el fin de semana" if pref_dias == FIN_DE_SEMANA else "entre semana"
        hora_txt = a_las(datetime(2000, 1, 1, h, mi))
        if not slots:
            return ofrecer(get_free_slots(n=3, dias_semana=pref_dias),
                           f"Uy{coma}, {cuando} {hora_txt} ya no tengo espacio 😕. Estos son los más cercanos:", _pie(meta, pide_fin))
        return ofrecer(slots, f"¡Claro que sí{coma}! 😊 Para {cuando} {hora_txt} tengo libre:", _pie(meta, pide_fin))
    if pref_dias and fh.get("fecha") is None and not rechaza:
        reprog = f"Sin problema{coma}, la reprogramamos 😊. " if meta.get("cita_agendada") else f"¡Claro que sí{coma}! 😊 "
        if pref_dias == FIN_DE_SEMANA:
            return ofrecer(_fin_de_semana(3), reprog + "El fin de semana te recibimos con todo gusto. Estos son los horarios más próximos:",
                           _pie(meta, pide_fin))
        if len(pref_dias) >= 4 and pref_dias != ENTRE_SEMANA:
            enc = reprog + f"Te busqué los horarios más próximos, sin contar {describir_dias(TODOS - pref_dias)}:"
        else:
            enc = reprog + f"Para {describir_dias(pref_dias)} tengo libre:"
        return ofrecer(get_free_slots(n=3, turno=fh.get("turno"), dias_semana=pref_dias), enc, _pie(meta, pide_fin))
    return None


def completar_fecha_por_contexto(fh, meta, coma, t=""):
    """'A eso de las 4.30' después de ofrecer el sábado => sábado 4:30. Si se ofrecieron varios días, pregunta cuál.
    Devuelve una respuesta (pregunta) o None; puede completar fh['fecha'] en el lugar."""
    if meta.get("ventana_noche_desde") and fh.get("hora") in (8, 9) and not re.search(r"\b(a\.? ?m|manana|temprano)\b", t) \
            and (fh.get("fecha") is None or fh["fecha"].weekday() < 5):
        fh["hora"] += 12  # le ofrecimos la noche: "a las 8" = 8 p. m.
    if fh.get("hora") is None and fh.get("fecha") is not None and meta.get("hora_pendiente"):
        hh, mm = meta.pop("hora_pendiente")
        fh["hora"], fh["minuto"] = hh, mm  # "el sábado" responde a "¿para qué día a las 4:30?"
        return None
    if fh.get("hora") is None or fh.get("fecha") is not None:
        return None
    if t and elegir_slot_ofrecido(t, meta.get("slots_ofrecidos") or [], {"hora": None, "fecha": None}) is not None:
        return None  # "la 1" es la opción 1, no la 1 p. m.
    hora_txt = a_las(datetime(2000, 1, 1, fh["hora"], fh.get("minuto") or 0))
    if meta.get("ventana_noche_desde") and fh["hora"] >= HORA_FIN_VISITAS:
        meta["hora_pendiente"] = [fh["hora"], fh.get("minuto") or 0]  # "a las 7" = de noche entre semana
        return _resp(f"¡Perfecto{coma}! ¿Qué día de la semana te acomoda {hora_txt}? 😊")
    vigentes = slots_vigentes(meta, ("ofrecio_horarios", "pregunto_dia"))
    fechas = sorted({s.date() for s in vigentes})
    if len(fechas) == 1:
        fh["fecha"] = fechas[0]
        return None
    if len(fechas) > 1:
        meta["hora_pendiente"] = [fh["hora"], fh.get("minuto") or 0]
        dias = [f"el {DIAS_ES[f.weekday()]} {f.day}" for f in fechas[:3]]
        opciones = ", ".join(dias[:-1]) + " o " + dias[-1]
        return _resp(f"¡Perfecto{coma}! ¿Para qué día {hora_txt}: {opciones}? 😊")
    return None


_TURNO_TXT = {"manana": " en la mañana", "tarde": " en la tarde", "noche": " en la noche"}


def _intro(meta, coma):
    """Saludo largo solo la 1ra vez; si ya tiene cita, se habla de CAMBIARLA (no de una visita nueva)."""
    try:
        cita = datetime.fromisoformat(meta["fecha_cita"]) if meta.get("cita_agendada") and meta.get("fecha_cita") else None
    except ValueError:
        cita = None
    if cita and cita > datetime.now(LIMA_TZ) and meta.get("aviso_cambio_cita") != meta.get("fecha_cita"):
        meta["aviso_cambio_cita"] = meta.get("fecha_cita")
        return f"¡Claro{coma}! Cambiamos tu visita del {DIAS_ES[cita.weekday()]} {cita.day} {a_las(cita)} sin problema 😊. "
    if cita and cita > datetime.now(LIMA_TZ):
        return f"¡Claro{coma}! 😊 "
    if not meta.get("saludo_visita"):
        meta["saludo_visita"] = True
        return f"¡Con todo gusto{coma}! 😊 Será un gusto recibirte en Urb. Santa Teresa (frente a la loza deportiva). "
    return f"¡Claro{coma}! 😊 "


def ofrecer_por_dia(fh, meta, ofrecer, coma, pie=""):
    """'Mejor el domingo', '¿el domingo 1 no tienes?', '¿para la tarde?' (sobre el día que se venía hablando)."""
    fecha, turno = fh.get("fecha"), fh.get("turno")
    hoy = datetime.now(LIMA_TZ).date()
    if fecha is None and turno and meta.get("dia_contexto"):
        try:
            d_ctx = datetime.fromisoformat(meta["dia_contexto"]).date()
            fecha = d_ctx if d_ctx >= hoy else None
        except ValueError:
            pass
    meta["dia_contexto"] = fecha.isoformat() if fecha else ""
    t_txt = _TURNO_TXT.get(turno, "")
    if fecha is None:
        return ofrecer(get_free_slots(n=3, turno=turno), _intro(meta, coma) + f"Estos son los horarios libres más próximos{t_txt}:", pie)
    dia_txt = f"el {DIAS_ES[fecha.weekday()]} {fecha.day}"
    if primer_dia_visitas() and fecha < primer_dia_visitas():
        meta["aviso_apertura"] = True
        meta["dia_contexto"] = ""
        return ofrecer(get_free_slots(n=3, turno=turno),
                       f"Te cuento{coma}: estamos dando los últimos detalles a las casas (pasamanos y barandas), así que las visitas "
                       f"las estamos agendando desde el {fecha_apertura_txt()} 😊. Estos son los primeros horarios libres{t_txt}:", pie)
    slots = get_free_slots(n=3, dia=fecha, turno=turno)
    enc = f"Para {dia_txt}{t_txt} tengo libre:"
    if not slots and turno:
        slots = get_free_slots(n=3, dia=fecha)
        enc = f"{dia_txt.capitalize()}{t_txt} ya no tengo espacio 😕, pero ese mismo día tengo:"
    if not slots:
        prox = fecha + timedelta(days=7)
        slots = get_free_slots(n=3, dia=prox, turno=turno)
        if slots:
            meta["dia_contexto"] = prox.isoformat()
            enc = f"Ese {DIAS_ES[fecha.weekday()]} ya no tengo espacios 😕, pero el siguiente, {DIAS_ES[prox.weekday()]} {prox.day}{t_txt}, tengo:"
    if not slots:
        slots = get_free_slots(n=3, turno=turno)
        enc = f"{dia_txt.capitalize()} ya no tengo espacios 😕. Estos son los más cercanos:"
    if meta.get("etapa") == "ofrecio_horarios" and [x.isoformat() for x in slots] == (meta.get("slots_ofrecidos") or []):
        return _ya_ofrecidos(slots, dia_txt + t_txt, coma)  # vuelve a preguntar por lo mismo: confirmar en corto, sin repetir la lista
    return ofrecer(slots, _intro(meta, coma) + enc, pie)


def _ya_ofrecidos(slots, cuando, coma):
    horas = [format_hora_es(x) for x in slots]
    lista = ", ".join(horas[:-1]) + " o " + horas[-1] if len(horas) > 1 else horas[0]
    r = _resp(f"¡Sí{coma}! 😊 Para {cuando} tengo libre a las {lista} ¿Cuál te reservo? (respóndeme 1, 2 o 3)")
    r["_sin_control_repeticion"] = True
    return r


def inferir_hora_suelta(t, fh, meta):
    """'Plan de 5?' (por 'para las 5'), '5?', 'de 4' con una lista de horarios a la vista: es una hora, no una opción ni otra cosa."""
    if fh.get("hora") is not None or meta.get("etapa") not in ("ofrecio_horarios", "pregunto_dia", "confirmar_horario") or len(t) > 25:
        return
    if elegir_slot_ofrecido(t, meta.get("slots_ofrecidos") or [], {"hora": None, "fecha": None, "turno": None}) is not None:
        return  # "2" con 3 opciones = la opción 2
    m = re.fullmatch(r"(?:[a-z]+ ){0,3}(\d{1,2})(?:[:.](\d{2}))?\s*(a ?m|p ?m)?(?: [a-z]+)?", t.strip())
    if not m or not 1 <= int(m.group(1)) <= 12:
        return
    h, ampm = int(m.group(1)), (m.group(3) or "").replace(" ", "")
    if (ampm == "pm" and h < 12) or (not ampm and 1 <= h <= 8):
        h += 12
    fh["hora"], fh["minuto"] = h, int(m.group(2) or 0)


def proponer_si_pregunta(slot, meta, coma):
    """'¿y a las 4?' es una PREGUNTA: se confirma que está libre y se pide el 'sí' (no se agenda de golpe). None si no está libre."""
    estado, _ = verificar_slot(slot)
    if estado not in ("libre", "sin_verificar"):
        return None
    meta.update({"slot_propuesto": slot.isoformat(), "etapa": "confirmar_horario"})
    accion = "¿Te cambio la visita a esa hora?" if meta.get("cita_agendada") else "¿Te la reservo?"
    r = _resp(f"¡Sí{coma}! El *{DIAS_ES[slot.weekday()]} {slot.day} {a_las(slot)}* está libre ✅ {accion} Respóndeme *sí* y listo.")
    r["_sin_control_repeticion"] = True
    return r


MAS_TARDE_RX = r"\b(mas tarde|mas tardecito|un poco mas tarde|algo mas tarde|mas en la tarde|mas noche|mas tardes?)\b"


def ofrecer_mas_tarde(t, user_text, meta, ofrecer, coma):
    """'¿Más tarde no podría ser?' con horarios a la vista = pide una hora MÁS TARDE ese mismo día (no es un rechazo)."""
    vigentes = slots_vigentes(meta)
    if not vigentes or not re.search(MAS_TARDE_RX, t) or re.search(r"\bmas tarde (te|le|les)\b|\bno puedo\b", t):
        return None
    # 'Más tarde no podría ser' (sin '?') es ambiguo y suele ser "más tarde no puedo": eso lo maneja el rechazo de siempre
    pregunta = "?" in (user_text or "") or (re.search(r"\b(puede ser|podria ser|seria posible|se puede|habra|hay|tienes|tiene|tendras|mejor)\b", t)
                                           and not re.search(r"\bno (podria|puedo|puede|podre)\b", t))
    if not pregunta:
        return None
    dia = vigentes[0].date()
    ultima = max(x.hour for x in vigentes if x.date() == dia)
    slots = get_free_slots(n=3, dia=dia, filtro=lambda dt: dt.hour > ultima)
    meta["ventana_noche_desde"] = HORA_INICIO_NOCHE
    noche = f"Y si te queda mejor aún más tarde, también te puedo recibir saliendo del trabajo, {HORARIO_NOCHE_HASTA_TXT}: dime la hora 😉"
    dia_txt = "hoy" if dia == datetime.now(LIMA_TZ).date() else f"el {DIAS_ES[dia.weekday()]} {dia.day}"
    if slots:
        meta["dia_contexto"] = dia.isoformat()
        return ofrecer(slots, f"¡Claro que sí{coma}! 😊 Más tarde, {dia_txt}, tengo libre:", noche)
    meta["dia_contexto"] = dia.isoformat()
    meta["etapa"] = "pregunto_dia"
    return _resp(f"¡Claro que sí{coma}! 😊 {dia_txt.capitalize()} en la tarde ya tengo la agenda llena, pero te puedo recibir saliendo del "
                 f"trabajo, desde las {_hora_txt(HORA_INICIO_NOCHE)} {HORARIO_NOCHE_HASTA_TXT}. ¿A qué hora te acomoda?")
