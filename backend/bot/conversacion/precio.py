"""Precio: moneda y tipo de cambio, el gancho del precio por m² y la respuesta a un tope de presupuesto."""
import re

from bot.config import (AREA_CONSTRUIDA_M2, PRECIO_CONTADO_USD, PRECIO_LISTA_USD, PRECIO_M2_DEPA_MAX, PRECIO_M2_DEPA_MIN,
                        PROPIETARIO_TXT, TIPO_CAMBIO_TEXTO)
from bot.conversacion.cierres import cierre_contextual
from bot.integraciones.tipo_cambio import tipo_cambio_referencial
from bot.nlp.patrones import DECLARA_MONTO_RE, MONEDA_PREGUNTA_RE, MONEDA_RE
from bot.utils.texto import _usd


def precio_m2(monto=None):
    return (monto or PRECIO_LISTA_USD) / AREA_CONSTRUIDA_M2


def _soles(x):
    return f"S/ {x:,.0f}"


def gancho_m2(meta, variante="corto"):
    """Una línea con el argumento del precio por m² (cuenta cuántas veces se usó para no repetirlo de más)."""
    meta["gancho_m2_n"] = int(meta.get("gancho_m2_n") or 0) + 1
    m2 = _usd(precio_m2())
    rango = f"{_usd(PRECIO_M2_DEPA_MIN)} y {_usd(PRECIO_M2_DEPA_MAX)}"
    if variante == "area":
        return f"Es decir, te sale a solo *{m2} por m² construido* 😉 (un depa en Chiclayo está entre {rango} por m²)."
    if variante == "seguimiento":
        return (f"Un dato que pocos comparan: estas casas salen a *{m2} por m²*, cuando un depa de 90 m² en Chiclayo está entre {rango} "
                "por m² y sin cochera, jardín ni terraza propia.")
    return (f"Son {AREA_CONSTRUIDA_M2:g} m² construidos a *{m2} por m²*, cuando un departamento en Chiclayo está entre {rango} por m² "
            "(y sin cochera, jardín ni terraza propia).")


def es_pregunta_moneda(t):
    return bool(MONEDA_RE.search(t) and MONEDA_PREGUNTA_RE.search(t) and not DECLARA_MONTO_RE.search(t))


def techo_soles(soles):
    """487,500 -> 'S/ 490,000' (el múltiplo de 5 mil inmediatamente superior), para decir 'por debajo de…'."""
    return _soles((int(soles) // 5000 + 1) * 5000)


def responder_moneda(t, nombre_corto, meta):
    """'¿El precio es en soles o en dólares?', '¿a qué tipo de cambio?', '¿puedo pagar en soles?'."""
    coma = f", {nombre_corto}" if nombre_corto else ""
    tc = tipo_cambio_referencial()
    ya = meta.get("ya_explicado") or []
    contado_pen = PRECIO_CONTADO_USD * (tc or 3.45)
    if "moneda" in ya:  # ya se le explicó lo del tipo de cambio: ir directo al número en soles
        meta["ya_explicado"] = list(set(ya + ["moneda"]))
        return (f"En soles{coma}, al contado te queda *por debajo de los {techo_soles(contado_pen)}* (aprox. {_soles(contado_pen)} "
                f"por los {_usd(PRECIO_CONTADO_USD)}), y ese precio lo puedes negociar directamente en la visita con {PROPIETARIO_TXT} 😉 "
                f"(el valor de lista, {_usd(PRECIO_LISTA_USD)}, equivale a unos {_soles(PRECIO_LISTA_USD * (tc or 3.45))}).\n\n"
                + cierre_contextual(meta, nombre_corto))
    partes = [f"¡Buena pregunta{coma}! 😊 Puedes hacer la operación en dólares o en soles: el valor de lista es "
              f"*{_usd(PRECIO_LISTA_USD)} USD* y, si pagas en soles, se toma {TIPO_CAMBIO_TEXTO}."]
    if tc:
        partes.append(f"Como referencia, a un tipo de cambio promedio de S/ {tc:.2f}, los {_usd(PRECIO_LISTA_USD)} equivalen a unos "
                      f"*{_soles(PRECIO_LISTA_USD * tc)}*. Pero al contado el precio es *{_usd(PRECIO_CONTADO_USD)}*, o sea que en soles "
                      f"te queda *por debajo de los {techo_soles(contado_pen)}* (aprox. {_soles(contado_pen)}), y es negociable en la "
                      f"visita con {PROPIETARIO_TXT} 😉")
    es_contado = meta.get("fin_modalidad") == "contado" or "contado" in str(meta.get("forma_pago") or "").lower()
    if not es_contado and "moneda" not in ya:
        partes.append("Si la compras con crédito hipotecario, el banco te puede prestar en soles o en dólares. Si tus ingresos son en soles, "
                      "normalmente conviene el crédito en soles, así tu cuota no cambia si sube el dólar (tu banco o nuestro asesor "
                      "hipotecario aliado te lo confirma sin costo).")
    meta["ya_explicado"] = list(set(ya + ["moneda"]))
    return "\n\n".join(partes) + "\n\n" + cierre_contextual(meta, nombre_corto)
