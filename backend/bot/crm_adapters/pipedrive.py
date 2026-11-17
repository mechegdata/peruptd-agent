"""PipedriveCRMAdapter (API v1 con api_token): catálogo desde /products; lead = Person + Deal; cita = Activity de tipo
'meeting'; resumen = Note. Credenciales: {"api_token_env": "PIPEDRIVE_TOKEN_<CLIENTE>", "dominio": "miempresa"}.
Mapeo opcional: {"catalogo": {...}, "lead": {"pago": "<hash del campo propio>"}, "stage_ids": {"booked": 3, ...}}."""
from datetime import timezone

from bot.crm_adapters.base import AdaptadorCRM, solo_digitos


class PipedriveCRMAdapter(AdaptadorCRM):
    nombre = "pipedrive"

    def _url(self, ruta):
        return f"https://{self.secreto('dominio', 'api')}.pipedrive.com/api/v1{ruta}"

    def _req(self, metodo, ruta, params=None, **kw):
        return self.http.request(metodo, self._url(ruta), params={**(params or {}), "api_token": self.secreto("api_token")}, timeout=20, **kw)

    def listar_productos(self):
        r = self._req("GET", "/products", {"limit": 200})
        if not self._ok(r, "la lectura de productos"):
            return []
        items = []
        for p in r.json().get("data") or []:
            precios = p.get("prices") or []
            if not precios:
                continue
            item = {"external_crm_id": str(p["id"]), "name_es": p.get("name"), "list_price": float(precios[0].get("price") or 0),
                    "currency": precios[0].get("currency") or "USD", "category": p.get("category"), "media": []}
            for clave, api in (self.campos.get("catalogo") or {}).items():
                if p.get(api) not in (None, ""):
                    item[clave] = p[api]
            items.append(item)
        return items

    def sincronizar_lead(self, ficha):
        return self._seguro(self._sincronizar, ficha)

    def _sincronizar(self, ficha):
        ids = ficha.get("crm_id") or ""
        persona, deal = (ids.split("|") + [None])[:2] if ids else (None, None)
        if not persona:
            r = self._req("GET", "/persons/search", {"term": solo_digitos(ficha.get("telefono"))[-9:], "fields": "phone", "limit": 1})
            hits = ((r.json().get("data") or {}).get("items") or []) if self._ok(r, "la búsqueda") else []
            persona = str(hits[0]["item"]["id"]) if hits else None
        datos = {"name": ficha.get("nombre") or "Lead", "phone": [{"value": ficha.get("telefono"), "primary": True}]}
        r = self._req("PUT", f"/persons/{persona}", json=datos) if persona else self._req("POST", "/persons", json=datos)
        if not self._ok(r, "la persona"):
            return None
        persona = persona or str(r.json()["data"]["id"])
        deal_datos = {"title": f"{ficha.get('nombre') or 'Lead'} — {ficha.get('producto') or 'OmniAgent'}", "person_id": int(persona),
                      **{api: ficha.get(c) for c, api in (self.campos.get("lead") or {}).items() if ficha.get(c) is not None}}
        if ficha.get("presupuesto"):
            deal_datos["value"] = ficha["presupuesto"]
        etapa = (self.campos.get("stage_ids") or {}).get(ficha.get("etapa"))
        if etapa:
            deal_datos["stage_id"] = etapa
        if ficha.get("etapa") in ("won", "lost"):
            deal_datos["status"] = ficha["etapa"]
        r = self._req("PUT", f"/deals/{deal}", json=deal_datos) if deal else self._req("POST", "/deals", json=deal_datos)
        deal = deal or (str(r.json()["data"]["id"]) if self._ok(r, "el deal") else "")
        return f"{persona}|{deal}"

    def registrar_cita(self, crm_id, inicio, minutos, asunto, descripcion="", ubicacion="", cita_id=None):
        persona, deal = ((crm_id or "").split("|") + [""])[:2]
        utc = inicio.astimezone(timezone.utc)
        datos = {"subject": asunto, "type": "meeting", "due_date": utc.strftime("%Y-%m-%d"), "due_time": utc.strftime("%H:%M"),
                 "duration": f"{minutos // 60:02d}:{minutos % 60:02d}", "note": descripcion, "location": ubicacion,
                 "person_id": int(persona) if persona else None, "deal_id": int(deal) if deal else None}
        datos = {k: v for k, v in datos.items() if v not in (None, "")}
        r = self._req("PUT", f"/activities/{cita_id}", json=datos) if cita_id else self._req("POST", "/activities", json=datos)
        return (cita_id or str(r.json()["data"]["id"])) if self._ok(r, "la actividad") else None

    def marcar_asistencia(self, cita_id, asistio, nota=""):
        r = self._req("PUT", f"/activities/{cita_id}", json={"done": 1 if asistio else 0, "public_description": nota or ("Attended" if asistio else "No-show")})
        return cita_id if self._ok(r, "la asistencia") else None

    def registrar_nota(self, crm_id, asunto, cuerpo):
        persona, deal = ((crm_id or "").split("|") + [""])[:2]
        datos = {"content": f"<b>{asunto}</b><br>{cuerpo}".replace("\n", "<br>")}
        datos.update({"deal_id": int(deal)} if deal else {"person_id": int(persona)})
        r = self._req("POST", "/notes", json=datos)
        return str(r.json()["data"]["id"]) if self._ok(r, "la nota") else None
