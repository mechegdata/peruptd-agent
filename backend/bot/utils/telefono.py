"""Normalización y extracción de teléfonos (Perú +51 e internacionales)."""
import re


# WhatsApp "usernames": algunos clientes llegan identificados por un BSUID ("PE.1000000000000001")
# en vez de su número. Ese ID se usa TAL CUAL (con el prefijo de país) y se envía en "recipient", no en "to".
BSUID_RE = re.compile(r"^[A-Z]{2}\.(?:ENT\.)?[A-Za-z0-9]{1,128}$")


def es_bsuid(valor):
    return bool(valor) and bool(BSUID_RE.match(str(valor).strip()))


def id_legado(valor):
    """Hasta nov-2026 el bot guardaba el BSUID sin el prefijo ("1000000000000001"). Sirve para recuperar el historial."""
    return str(valor).strip().rsplit(".", 1)[-1] if es_bsuid(valor) else None


def destino_wa(destino):
    """Campo de destinatario para la Cloud API: {"to": teléfono} o {"recipient": BSUID}."""
    if es_bsuid(destino):
        return {"recipient": str(destino).strip()}
    return {"to": normalize_pe_phone(destino) or str(destino).replace("+", "")}


def normalize_pe_phone(raw):
    if not raw:
        return None
    if es_bsuid(raw):
        return str(raw).strip()
    digs = re.sub(r"\D", "", str(raw))
    if digs.startswith("00"):
        digs = digs[2:]
    if len(digs) == 9 and digs.startswith("9"):
        return "51" + digs
    if len(digs) == 11 and digs.startswith("519"):
        return digs
    if len(digs) >= 10:
        return digs  # número internacional (cliente en el extranjero): no se modifica
    return None


def extract_phone_from_text(text):
    if not text:
        return None
    m = re.search(r"(?:\+?51)?\s*(9(?:[\s\-]*\d){8})", text)
    if m:
        return normalize_pe_phone(m.group(0))
    return None
