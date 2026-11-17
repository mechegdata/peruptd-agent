"""Expresiones regulares de intención (visita, material, afirmación, negación, despedida, etc.)."""
import re


# =====================================================================
# MOTOR DE AGENDA DETERMINÍSTICO
# Se ejecuta ANTES de Gemini para los mensajes de agendamiento, así la
# cita se concreta aunque el LLM falle. Guarda el estado en leads.interes:
#   etapa: ofrecio_horarios | pregunto_financiamiento | confirmar_horario | agendado
#   slot_propuesto, slots_ofrecidos, fin_modalidad, fin_inicial,
#   fin_credito_aprobado, pregunta_fin_pendiente, cita_agendada, fecha_cita, evento_id
# =====================================================================
DIAS_IDX = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}


MESES_IDX = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}
_DIAS_RX = "lunes|martes|miercoles|jueves|viernes|sabado|domingo"
_MESES_RX = "|".join(MESES_IDX.keys())
_AMPM_RX = r"(a\.?\s?m|p\.?\s?m)\.?(?![a-z])"


VISITA_RE = re.compile(
    r"\b(visita\w*|visitar\w*|agend\w*|cita|recorr\w*|horarios?|disponibilidad|conocer\w*|mirar\w*|"
    r"ir a ver\w*|pasar a ver|dar(?:me|nos)? una vuelta|puedo ir|podemos ir|podria ir|quiero ir|queremos ir|"
    r"(?:gustaria|quisiera|quisieramos|podriamos) (?:ir|pasar|acercarme|acercarnos)|acercarme a ver|"
    r"cuando puedo|cuando podria|a que hora|verlas|verla|"
    r"ver (?:la|las|el|los|esa|esas) (?:casas?|propiedad\w*|inmuebles?|viviendas?|proyecto|unidad\w*))\b"
)
VISITA_FUERTE_RE = re.compile(r"\b(visita\w*|visitar\w*|agend\w*|cita|ir a ver\w*|quiero ir|puedo ir|recorr\w*)\b")
MATERIAL_RE = re.compile(r"\b(plano\w*|ficha\w*|render\w*|fotos?|fotitos?|fotografias?|pdf|imagen\w*|video\w*|distribucion|cocinas?|reposteros?|brochure|catalogo)\b")


POSTERGAR_RE = re.compile(
    r"\b(te|le|les) (confirmo|aviso|escribo|llamo|comento|respondo|comunico|digo|confirmamos|avisamos|escribimos)\b|"
    r"\blo (pienso|consulto|converso|voy a pensar|evaluo|vemos|coordino|coordinamos|hablamos)\b|"
    r"\b(despues|luego|mas tarde) (te|le)\b|"
    r"\b(te|le|les) (estare|estaria|estaremos|voy a|vamos a) (confirmando|avisando|escribiendo|comunicando|llamando|comentando|"
    r"confirmar|avisar|escribir|comunicar|llamar|comentar)\b|"
    r"\b(voy a|tengo que|debo|vamos a) (consultar|conversar|hablar|coordinar|ver)(lo)? con\b|"
    r"\bcuando (sepa|tenga (la hora|el dia|tiempo)|confirme|me desocupe)\b|"
    r"\bcuando (vaya|voy|venga|vengo|llegue|baje|regrese|vuelva|este por (alla|aca|ahi))\b"
)
# "Yo estoy en Jaén, cuando voy los visito": vive lejos (se le ofrece el video y se le espera, sin lista de horarios)
LEJOS_RE = re.compile(r"\b(?:estoy|vivo|me encuentro|ando|radico|trabajo) (?:en|por) (?!la |el |los |las |mi |un |una |casa|oficina|trabajo|clase)"
                      r"([a-zñáéíóú]+(?: de [a-zñáéíóú]+)?)")
# Acuse corto sin contenido ("ok", "listo", "👍"). Los "gracias" los maneja la despedida.
ACUSE_RE = re.compile(r"^(ok+|okey|okay|ya|ya ya|listo|vale|perfecto|entendido|de acuerdo|muy bien|bien|genial|excelente|super|dale|bueno)$")


# "Si me indica qué día" / "si puede mañana" es un SI condicional (if), no un "sí": no cuenta como afirmación
SI_CONDICIONAL = (r"(?!si (?:me|nos|le|les) (?:indica|indican|indicas|dice|dicen|dices|avisa|avisan|avisas|manda|mandan|mandas|envia|"
                  r"envian|envias|pasa|pasan|pasas|puede|pueden|puedes|podria|podrian|podrias|ayuda|ayudan|ayudas|confirma|"
                  r"confirman|confirmas|separa|separan|reserva|reservan|explica|explican)\b)"
                  r"(?!si (?:usted|ustedes|puede|pueden|puedes|podria|podrian|podrias|quiere|quieres|gusta|gustas|desea|deseas|"
                  r"hay|habria|tiene|tienen|tienes|fuera|es posible|se puede|no es molestia)\b)")
AFIRMA_RE = re.compile(
    r"^" + SI_CONDICIONAL + r"(si+|sip|claro|ok+|okey|okay|dale|perfecto|listo|de acuerdo|confirmo|confirmado|va|ya|esta bien|"
    r"me parece bien|excelente|genial|correcto|por supuesto|sale|bueno|mantenla|mantengala|mantenlo|reservala|agendala)\b"
)


NIEGA_RE = re.compile(
    r"^(no+|nop|nope|todavia no|aun no|no todavia|no aun|tampoco|nada aun|aun nada|todavia nada|"
    r"no tengo|todavia|aun)\b"
)


RECHAZO_RE = re.compile(
    r"^(ninguno|ninguna|ningun|ni uno|ni una|tampoco|esos no|esas no|no me (acomoda|queda|conviene|sirve|alcanza)|"
    r"no puedo|no podre|no podria|no estoy|no,? otro|no,? otra|otro dia|otra hora|otro horario|otra fecha)\b|"
    r"\b(ninguno|ninguna) (me|de)\b|\bno me (acomoda|acomodan|quedan?|conviene|convienen|sirven?)\b|"
    r"\b(otro dia|otros dias|otro horario|otros horarios|otra fecha|mas adelante|mas tarde no)\b"
)


PREGUNTA_INFO_RE = re.compile(
    r"\b(como seria|como es|como funciona|como hago|cuanto seria|cuanto es|cuanto deberia|cuanto necesito|cuanto tendria|"
    r"cuanto pagaria|que necesito|cuales son|una consulta|requisitos|procedimiento|proceso|se puede financiar|"
    r"tienen financiamiento|hay financiamiento|dan financiamiento|financian|financiar|facilidades|credito directo|en cuotas|a plazos)\b"
)
NEG_CLAUSULA_RE = re.compile(r"\b(no|sin|ni|tampoco|todavia no|aun no|nada)\b")


DESPEDIDA_RE = re.compile(
    r"^(no+,? (muchas |mil )?gracias|no,? eso (es|seria) todo|no,? nada mas|no,? ninguna|no,? por ahora( no)?|nada mas|eso es todo|eso seria todo|"
    r"seria todo|todo claro|todo bien,? gracias|(ok|okey|okay|ya|listo|perfecto|genial|excelente|bueno|bien|muy bien|entendido|vale|super)\W*,? (muchas |mil )?gracias|"
    r"(muchas |mil |muchisimas )?gracias+( por (todo|la informacion|la info|su tiempo|tu tiempo|su atencion|tu ayuda))?|"
    r"chao+|chau+|adios|hasta luego|hasta pronto|bendiciones|igualmente|gracias,? igualmente)\W*"
    r"(\s*(muy amable|que tenga\w* (un )?buen\w* (dia|tarde|noche)|bendiciones|saludos|igualmente|👍|🙏|😊))*\W*$"
)
PREGUNTA_OTRA_DUDA_RE = re.compile(r"(?i)(otra|alguna|mas) (duda|pregunta|consulta)|en qu[eé] m[aá]s te puedo ayudar|algo m[aá]s en (lo )?que")


NO_INTERESADO_RE = re.compile(
    r"\b(no me interesa|ya no me interesa|ya no estoy interesad\w*|no estoy interesad\w*|ya compre|ya compramos|ya adquiri\w*|"
    r"dejen de escribir\w*|no me escriban|no me escribas|no molest\w*|borren mi numero|no deseo recibir|no quiero recibir|stop)\b"
)


# ---------------- Precio: moneda / tipo de cambio y objeción "está caro" ----------------
MONEDA_RE = re.compile(r"\b(tipo de cambio|cambio del dia|que moneda|en que moneda|soles|dolares|dolar|usd|moneda)\b")
MONEDA_PREGUNTA_RE = re.compile(
    r"\b(tipo de cambio|cambio del dia|moneda|en soles|en dolares|o soles|o dolares|o en soles|o en dolares|aceptan|"
    r"puedo pagar|se puede pagar|podria pagar|pagar en|cuanto (es|seria|sale|saldria|esta|son) en|precio en|"
    r"esta en|es en|son en|equivale|al cambio)\b"
)
DECLARA_MONTO_RE = re.compile(r"\b(tengo|tenemos|cuento con|contamos con|dispongo|disponemos|ahorrad\w*|junte|juntamos)\b")
OBJECION_PRECIO_RE = re.compile(
    r"\b(muy car[oa]s?|car[oa]s?|carisim\w*|costos[oa]|salad[oa]|elevad[oa]|excesiv[oa]|mucho dinero|mucha plata|"
    r"es mucho(?! mas)|es demasiado|esta muy alto|un poco alto|algo alto|muy alto|bastante alto|esta fuerte|"
    r"(?:sigue siendo|igual es|me parece|es) (?:mucho|demasiado) para mi|no puedo pagar tanto|no me da el presupuesto|"
    r"fuera de mi (presupuesto|alcance|rango)|se me pasa|se pasa de mi presupuesto|"
    r"no me alcanza(?! (el|la|los) (tiempo|hora|dia))|no llego (al|a ese) (precio|monto)|no estoy en ese rango|"
    r"no esta en mi (presupuesto|rango)|algo mas barat\w*|mas barat\w*|mas economic\w*|no tengo tanto)\b"
)
NO_OBJECION_RE = re.compile(r"\b(no (es|esta|me parece|lo veo|la veo|se ve) (tan |muy )?car[oa]|cara a (la|el)|de cara)\b")


# ---------------- Comandos del asesor (escribiendo al número del bot desde OWNER_WA) ----------------
COMANDO_RE = re.compile(r"^\s*(si vino|vino|realizada|asistio|no vino|no asistio|falto|pausa|pausar|activar|reanudar|vendido|vendida|estado)\s+\+?([\d\s]{9,15})\s*$", re.I)
