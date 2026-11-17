"""HubSpotCRMAdapter (API v3 con token de Private App): catálogo desde crm/v3/objects/products; el lead se escribe como
Contact + Deal asociado; la cita como Meeting y el resumen como Note (asociados al contacto).
Credenciales: {"token_env": "HUBSPOT_TOKEN_<CLIENTE>"}. Mapeo opcional: {"catalogo": {...}, "lead": {...},
"deal_stages": {"booked": "appointmentscheduled", ...}, "pipeline": "default"}."""
import time

from bot.crm_adapters.base import AdaptadorCRM, solo_digitos

API = "https://api.hubapi.com"
ETAPAS = {"new": "appointmentscheduled", "qualified": "qualifiedtobuy", "booked": "presentationscheduled",
          "visited": "decisionmakerboughtin", "negotiation": "contractsent", "won": "closedwon", "lost": "closedlost"}


class HubSpotCRMAdapter(AdaptadorCRM):
    nombre = "hubspot"

    def _h(self):
        return {"Authorization": f"Bearer {self.secreto('token')}", "Content-Type": "application/json"}

    def _req(self, metodo, ruta, **kw):
        return self.http.request(metodo, API + ruta, headers=self._h(), timeout=20, **kw)

    def listar_productos(self):
        extra = list((self.campos.get("catalogo") or {}).values())
        r = self._req("GET", "/crm/v3/objects/products", params={"limit": 100, "properties": ",".join(["name", "price", "description", "hs_sku"] + extra)})
        if not self._ok(r, "la lectura de productos"):
            return []
        items = []
        for p in r.json().get("results", []):
            pr = p.get("properties") or {}
            if pr.get("price") in (None, ""):
                continue
            item = {"external_crm_id": p["id"], "name_es": pr.get("name"), "list_price": float(pr["price"]), "media": []}
            for clave, api in (self.campos.get("catalogo") or {}).items():
                if pr.get(api) not in (None, ""):
                    item[clave] = pr[api]
            items.append(item)
        return items

    def _buscar_contacto(self, telefono):
        cuerpo = {"filterGroups": [{"filters": [{"propertyName": "phone", "operator": "CONTAINS_TOKEN", "value": solo_digitos(telefono)[-10:]}]}], "limit": 1}
        r = self._req("POST", "/crm/v3/objects/contacts/search", json=cuerpo)
        res = r.json().get("results", []) if self._ok(r, "la búsqueda de contacto") else []
        return res[0]["id"] if res else None

    def sincronizar_lead(self, ficha):
        return self._seguro(self._sincronizar, ficha)

    def _sincronizar(self, ficha):
        ids = ficha.get("crm_id") or ""
        contacto, deal = (ids.split("|") + [None])[:2] if ids else (None, None)
        contacto = contacto or self._buscar_contacto(ficha.get("telefono"))
        nombre = (ficha.get("nombre") or "").split(" ", 1)
        props = {"firstname": nombre[0], "lastname": nombre[1] if len(nombre) > 1 else "", "phone": ficha.get("telefono"),
                 "hs_language": ficha.get("idioma"), **{api: ficha.get(c) for c, api in (self.campos.get("lead") or {}).items() if ficha.get(c) is not None}}
        props = {k: v for k, v in props.items() if v not in (None, "")}
        r = self._req("PATCH", f"/crm/v3/objects/contacts/{contacto}", json={"properties": props}) if contacto \
            else self._req("POST", "/crm/v3/objects/contacts", json={"properties": props})
        if not self._ok(r, "el contacto"):
            return None
        contacto = contacto or r.json()["id"]
        etapas = {**ETAPAS, **(self.campos.get("deal_stages") or {})}
        deal_props = {"dealname": f"{ficha.get('nombre') or 'Lead'} — {ficha.get('producto') or 'OmniAgent'}",
                      "dealstage": etapas.get(ficha.get("etapa"), etapas["new"]), "pipeline": self.campos.get("pipeline", "default")}
        if ficha.get("presupuesto"):
            deal_props["amount"] = ficha["presupuesto"]
        if deal:
            self._req("PATCH", f"/crm/v3/objects/deals/{deal}", json={"properties": deal_props})
        else:
            r = self._req("POST", "/crm/v3/objects/deals", json={"properties": deal_props, "associations": [
                {"to": {"id": contacto}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}]}]})
            deal = r.json().get("id") if self._ok(r, "el deal") else None
        return f"{contacto}|{deal or ''}"

    def registrar_cita(self, crm_id, inicio, minutos, asunto, descripcion="", ubicacion="", cita_id=None):
        contacto = (crm_id or "").split("|")[0]
        fin = int(inicio.timestamp() * 1000) + minutos * 60000
        props = {"hs_timestamp": int(inicio.timestamp() * 1000), "hs_meeting_title": asunto, "hs_meeting_body": descripcion,
                 "hs_meeting_location": ubicacion, "hs_meeting_start_time": int(inicio.timestamp() * 1000), "hs_meeting_end_time": fin,
                 "hs_meeting_outcome": "SCHEDULED"}
        if cita_id:
            r = self._req("PATCH", f"/crm/v3/objects/meetings/{cita_id}", json={"properties": props})
            return cita_id if self._ok(r, "la reprogramación") else None
        r = self._req("POST", "/crm/v3/objects/meetings", json={"properties": props, "associations": [
            {"to": {"id": contacto}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 200}]}]})
        return r.json().get("id") if self._ok(r, "la reunión") else None

    def marcar_asistencia(self, cita_id, asistio, nota=""):
        r = self._req("PATCH", f"/crm/v3/objects/meetings/{cita_id}", json={"properties": {"hs_meeting_outcome": "COMPLETED" if asistio else "NO_SHOW"}})
        return cita_id if self._ok(r, "la asistencia") else None

    def registrar_nota(self, crm_id, asunto, cuerpo):
        contacto = (crm_id or "").split("|")[0]
        r = self._req("POST", "/crm/v3/objects/notes", json={"properties": {"hs_timestamp": int(time.time() * 1000), "hs_note_body": f"{asunto}\n\n{cuerpo}"},
                                                               "associations": [{"to": {"id": contacto}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]}]})
        return r.json().get("id") if self._ok(r, "la nota") else None
