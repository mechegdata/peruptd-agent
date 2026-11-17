"""Primer mensaje a leads que llenaron el formulario de Meta."""
import re
from datetime import datetime, timedelta, timezone

from bot.config import PRECIO_LISTA_USD
from bot.conversacion.cierres import _cierre_con_horarios
from bot.conversacion.material import ESTILOS_TXT, _estilo_de_texto
from bot.nlp.financiamiento import detectar_financiamiento, estado_financiero
from bot.utils.texto import _usd, limpiar_texto


def marcar_bienvenida(meta):
    meta["bienvenida_ts"] = datetime.now(timezone.utc).isoformat()
    meta["wsp_iniciado"] = True


def bienvenida_reciente(meta, dias=3):
    """True si ya se le mandó la bienvenida del formulario hace menos de 'dias' (Meta a veces avisa 2 veces del mismo formulario:
    el mensaje de WhatsApp y el aviso de Lead Ads, o reintenta el webhook)."""
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(meta.get("bienvenida_ts") or "") < timedelta(days=dias)
    except ValueError:
        return False


def texto_formulario(nombre, cocina, pago, presupuesto, meta):
    """Respuesta a un lead del formulario de Meta según lo que marcó (pago, estilo de cocina y presupuesto)."""
    nom = (nombre or "").split()[0].title() if nombre and nombre not in ["Cliente", "Interesado"] else ""
    coma = f", {nom}" if nom else ""
    d = detectar_financiamiento(pago or "")
    pl = limpiar_texto(pago or "")
    if re.search(r"\b(aun no|todavia no|sin inicial|ni evaluacion|no cuento)\b", pl):
        d["inicial"], d["credito_aprobado"] = False, False
    if re.search(r"pre ?aprobad", pl):
        d["credito_aprobado"], d["modalidad"] = True, "credito"
    for k_src, k_meta in (("modalidad", "fin_modalidad"), ("inicial", "fin_inicial"), ("credito_aprobado", "fin_credito_aprobado")):
        if d[k_src] is not None:
            meta[k_meta] = d[k_src]
    meta["forma_pago"] = pago or meta.get("forma_pago")
    estilo = _estilo_de_texto(cocina or "")
    if estilo:
        meta["estilo_cocina"] = ESTILOS_TXT[estilo]
    estilo_txt = f"la {ESTILOS_TXT[estilo]}" if estilo else "tu diseño de cocina"
    presup_no = limpiar_texto(presupuesto or "").startswith("no")
    calif = estado_financiero(meta)
    flags = {"enviar_ficha_tecnica": True, "enviar_renders_cocina": True, "estilo_render_preferido": estilo or "ambos"}
    intro = (f"¡Hola{coma}! 😊 Te saluda el equipo de SAGUE Constructora. Gracias por completar el formulario de nuestras 2 casas de estreno "
             "en Urb. Santa Teresa, Lambayeque (200 m² construidos en 3 pisos, frente a la loza deportiva, entrega inmediata con título en SUNARP).\n\n")
    if calif is False:
        meta["etapa"] = "ofrecio_asesor"
        meta["ya_explicado"] = list(set((meta.get("ya_explicado") or []) + ["sin_inicial"]))
        txt = (intro + f"¡Muy buena elección {estilo_txt} para tus reposteros! Te comparto los planos de distribución y el render de ese diseño.\n\n"
               "Vi que aún no cuentas con inicial ni evaluación bancaria. Como las casas ya están construidas y con título en SUNARP, la compra es al contado o con "
               f"crédito hipotecario de cualquier banco, que pide desde el 10% de inicial (aprox. {_usd(PRECIO_LISTA_USD * 0.10)} USD); no manejamos crédito directo.\n\n"
               "¿Tienes proyectado disponer pronto de esa inicial? Si gustas, nuestro asesor hipotecario aliado te evalúa *sin costo* y te dice cuánto "
               "te financian. Respóndeme *sí* y le paso tus datos.")
    elif presup_no:
        meta["etapa"] = "pregunto_presupuesto"
        txt = (intro + f"¡Muy buena elección {estilo_txt}! Te comparto los planos y el render de ese diseño.\n\n"
               f"Vi que el valor de lista ({_usd(PRECIO_LISTA_USD)}) se escapa un poco de tu rango. Como la 1ra unidad tiene un Bono Especial de Lanzamiento "
               "(e incluso podemos entregarla sin los reposteros y descontar ese monto), cuéntame con total confianza: "
               "¿cuál es el tope aproximado de inversión o crédito que manejas? Así vemos si llegamos a un número que te encaje.")
    else:
        modalidad = ("al contado" if meta.get("fin_modalidad") == "contado" else
                     "con tu crédito preaprobado" if meta.get("fin_credito_aprobado") else
                     "con tu inicial lista" if meta.get("fin_inicial") else "")
        if estilo:
            material = f"¡Excelente elección {estilo_txt} para tus reposteros! Te comparto los planos de los 3 pisos y el render de ese diseño."
        else:  # el formulario llegó sin las respuestas (solo el saludo): no inventar lo que eligió
            material = ("Te comparto los planos de los 3 pisos y los 2 diseños de cocina que entregamos instalados "
                        "(Gris Grafito con LED o Madera Rovere): ¿cuál te gusta más?")
        bono = (f"Como compras {modalidad}, tienes *prioridad para el Bono Especial de Lanzamiento de la 1ra Unidad* sobre el valor de lista "
                f"de {_usd(PRECIO_LISTA_USD)}." if modalidad else
                f"La 1ra unidad que se separe tiene el *Bono Especial de Lanzamiento* sobre el valor de lista de {_usd(PRECIO_LISTA_USD)}.")
        txt = intro + material + "\n\n" + bono + "\n\n" + _cierre_con_horarios(meta, nom)
    return txt, flags
