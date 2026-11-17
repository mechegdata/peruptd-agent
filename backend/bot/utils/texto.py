"""Normalización de texto (tildes, minúsculas) y formatos simples."""
import re
import unicodedata


def sin_tildes(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def limpiar_texto(s):
    t = sin_tildes(s)
    t = re.sub(r"[¿?¡!\"“”]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _usd(x):
    return f"${x:,.0f}"


# Nombres de pila frecuentes: si el perfil es 'Chonate Alcoser Jorge' (apellidos primero), se usa 'Jorge'
NOMBRES_COMUNES = set("""jorge juan jose luis carlos miguel pedro manuel jesus david daniel victor cesar oscar julio mario raul hugo javier
ricardo roberto fernando alberto eduardo francisco antonio alex alexander andres diego henry ivan jhon john jhonny jaime walter wilmer
segundo santos william edwin elmer nilton percy rosa maria ana carmen julia luz elena patricia sandra silvia monica gloria teresa
lucia diana karina katherine milagros flor jessica yesenia liliana marleny marisol veronica gabriela claudia sofia valeria""".split())


def _orden_nombre(nombre):
    partes = nombre.split()
    if len(partes) >= 3 and sin_tildes(partes[0]) not in NOMBRES_COMUNES and sin_tildes(partes[-1]) in NOMBRES_COMUNES:
        return " ".join([partes[-1]] + partes[:-1])
    return nombre


def nombre_valido(nombre):
    """El nombre de perfil de WhatsApp puede ser '.', '😊' o '~Brayan': se limpian símbolos y solo se usa si tiene al menos 2 letras."""
    nombre = re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúÑñÜü' -]+", " ", nombre or "")
    nombre = re.sub(r"\s+", " ", nombre).strip(" -'")
    if nombre.isupper() or nombre.islower():
        nombre = nombre.title()  # 'JUAN CORONEL' -> 'Juan Coronel'; 'gladis' -> 'Gladis'
    return _orden_nombre(nombre) if len(re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", nombre)) >= 2 else ""


def _primer_nombre(nombre):
    nombre = nombre_valido(nombre)
    return nombre.split()[0].title() if nombre and nombre not in ["Interesado", "Cliente"] else ""
