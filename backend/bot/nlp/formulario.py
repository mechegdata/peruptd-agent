"""Lectura del texto de formularios Lead Ads de Meta que llegan por chat."""
import re

from bot.utils.telefono import normalize_pe_phone


def parse_lead_form_text(text):
    if not text:
        return {}
    low = text.lower()
    if "filled out your form" not in low and "completé el formulario" not in low and "cómo planeas realizar la compra" not in low:
        return {}
    info = {"es_formulario": True}
    m_name = re.search(r"(?i)full name:\s*([^\n\r]+)", text)
    if m_name:
        info["nombre"] = m_name.group(1).strip().title()
    m_phone = re.search(r"(?i)phone number:\s*([^\n\r]+)", text)
    if m_phone:
        info["telefono"] = normalize_pe_phone(m_phone.group(1))
    m_pago = re.search(r"(?i)c[oó]mo planeas realizar la compra\?:\s*([^\n\r]+)", text)
    if m_pago:
        info["forma_pago"] = m_pago.group(1).strip()
    m_cocina = re.search(r"(?i)qu[eé] estilo prefieres\?:\s*([^\n\r]+)", text)
    if m_cocina:
        info["estilo_cocina"] = m_cocina.group(1).strip()
    m_presup = re.search(r"(?i)rango de inversi[oó]n\?:\s*([^\n\r]+)", text)
    if m_presup:
        info["en_presupuesto"] = m_presup.group(1).strip()
    return info
