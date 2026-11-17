"""Verificación de la firma X-Hub-Signature-256 que Meta pone en cada aviso del webhook."""
import hashlib
import hmac


def firma_valida(cuerpo, cabecera, secretos):
    """True si `cabecera` ("sha256=<hex>") es el HMAC-SHA256 de `cuerpo` (bytes) con alguno de los `secretos`."""
    if not cabecera or not cabecera.startswith("sha256="):
        return False
    recibida = cabecera.split("=", 1)[1].strip().lower()
    for secreto in secretos:
        esperada = hmac.new(secreto.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
        if hmac.compare_digest(esperada, recibida):
            return True
    return False
