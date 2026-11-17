"""Utilidades de redacción bilingüe (Capa 3)."""


def L(idioma, en, es):
    return es if idioma == "es" else en


def dinero(monto, idioma, moneda="USD"):
    simbolo = {"USD": "US$" if idioma == "es" else "$", "PEN": "S/ ", "MXN": "MX$", "COP": "COP$", "EUR": "€"}.get(moneda, moneda + " ")
    return f"{simbolo}{round(monto):,}"


def campo(item, base, idioma):
    """item['promo_bonus_es'] / item['promo_bonus_en'] con respaldo al otro idioma."""
    return item.get(f"{base}_{idioma}") or item.get(f"{base}_es") or item.get(f"{base}_en") or ""


def nombre(item, idioma):
    return item.get(f"name_{idioma}") or item.get("name_es") or item.get("name_en") or ""
