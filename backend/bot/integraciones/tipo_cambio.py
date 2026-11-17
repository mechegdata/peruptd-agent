"""Tipo de cambio referencial PEN/USD: se actualiza solo desde el BCRP (interbancario venta) y, si falla, usa el número fijo."""
import json
import time
from datetime import datetime, timedelta

import requests

from bot.config import LIMA_TZ, TIPO_CAMBIO_AUTO, TIPO_CAMBIO_REFERENCIAL

_CACHE = {"ts": 0.0, "valor": None, "ultimo_bueno": None}
_TTL_OK = 6 * 3600   # se refresca como máximo 4 veces al día
_TTL_FALLO = 3600
# Serie del BCRP: tipo de cambio interbancario, venta (S/ por US$)
_URL_BCRP = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04640PD/json/{desde}/{hasta}"


def _consultar_bcrp():
    hoy = datetime.now(LIMA_TZ).date()
    url = _URL_BCRP.format(desde=(hoy - timedelta(days=10)).isoformat(), hasta=hoy.isoformat())
    r = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0 (sague-bot)", "Accept": "application/json"})
    data = json.loads(r.text.lstrip("﻿"))
    for periodo in reversed(data.get("periods") or []):
        for v in periodo.get("values") or []:
            try:
                valor = float(str(v).replace(",", "."))
            except ValueError:
                continue
            if 2.5 < valor < 6:  # sanidad: descarta 'n.d.' o datos raros
                return valor
    return None


def tipo_cambio_referencial():
    """S/ por US$ para dar montos aproximados en soles. Con TIPO_CAMBIO_AUTO (por defecto) usa el BCRP del día;
    si el BCRP no responde, el último valor bueno; y si nunca respondió, TIPO_CAMBIO_REFERENCIAL. None = no dar cifras en soles."""
    if not TIPO_CAMBIO_AUTO:
        return TIPO_CAMBIO_REFERENCIAL or None
    ahora = time.time()
    ttl = _TTL_OK if _CACHE["valor"] else _TTL_FALLO
    if not (_CACHE["ts"] and ahora - _CACHE["ts"] < ttl):
        try:
            valor = _consultar_bcrp()
        except Exception as e:
            print("No se pudo leer el tipo de cambio del BCRP:", str(e)[:150])
            valor = None
        if valor:
            if valor != _CACHE["ultimo_bueno"]:
                print(f"Tipo de cambio BCRP actualizado: S/ {valor:.4f}")
            _CACHE["ultimo_bueno"] = valor
        _CACHE.update(ts=ahora, valor=valor)
    return round(_CACHE["valor"] or _CACHE["ultimo_bueno"] or TIPO_CAMBIO_REFERENCIAL or 0, 2) or None
