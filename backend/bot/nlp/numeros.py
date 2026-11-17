"""Montos escritos en palabras ('cuatrocientos mil ochocientos', 'ciento veinte mil') -> número.

Aprendido de chats reales: hay clientes que dictan por voz y el monto llega en letras.
"""
import re

_UNIDADES = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
    "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21, "veintiuno": 21, "veintidos": 22, "veintitres": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
    "cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200, "trescientos": 300, "trescientas": 300,
    "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500, "quinientas": 500, "seiscientos": 600, "seiscientas": 600,
    "setecientos": 700, "setecientas": 700, "ochocientos": 800, "ochocientas": 800, "novecientos": 900, "novecientas": 900,
}


def numero_en_palabras(t):
    """Primer número escrito en letras dentro del texto (ya limpio, sin tildes). None si no hay ninguno de 1,000 o más."""
    palabras = re.findall(r"[a-z]+", t or "")
    total, actual, visto, en_numero = 0, 0, False, False
    for p in palabras:
        if p in _UNIDADES:
            actual += _UNIDADES[p]
            visto = en_numero = True
        elif p == "y" and en_numero:
            continue
        elif p == "mil" and en_numero or (p == "mil" and not visto):
            total += (actual or 1) * 1000
            actual, visto, en_numero = 0, True, True
        elif p in ("millon", "millones") and visto:
            total = (total + (actual or 1)) * 1000000
            actual = 0
        elif en_numero:
            if total + actual >= 1000:
                break  # terminó el número
            total, actual, visto, en_numero = 0, 0, False, False  # 'un presupuesto de cien mil': 'un' no era el monto
    valor = total + actual
    return valor if visto and valor >= 1000 else None
