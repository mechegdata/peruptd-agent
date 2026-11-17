"""ZohoCRMAdapter (API v6, OAuth con refresh token): catálogo desde Products; lead en Leads (upsert por teléfono);
cita en Events; resumen en Notes. Credenciales: {"client_id_env": ..., "client_secret_env": ..., "refresh_token_env": ...,
"dominio": "com" | "eu" | "in" | ...}. Mapeo opcional: {"catalogo": {...}, "lead": {...}, "estados": {"booked": "Contacted"}}."""
import time
from datetime import datetime

from bot.crm_adapters.base import AdaptadorCRM

ESTADOS = {"new": "Not Contacted", "qualified": "Contacted", "booked": "Contacted", "visited": "Contacted",
           "negotiation": "Contact in Future", "won": "Pre-Qualified", "lost": "Lost Lead"}


class ZohoCRMAdapter(AdaptadorCRM):
    nombre = "zoho"

    def _dom(self):
        return self.secreto("dominio", "com")

    def _access(self):
        tok = self.token_vigente(3300)
        if tok:
            return tok
        r = self.http.post(f"https://accounts.zoho.{self._dom()}/oauth/v2/token", timeout=15, params={
            "refresh_token": self.secreto("refresh_token"), "client_id": self.secreto("client_id"),
            "client_secret": self.secreto("client_secret"), "grant_type": "refresh_token"})
        if not self._ok(r, "el token OAuth"):
            raise RuntimeError("Zoho no entregó token")
        self._token.update(valor=r.json()["access_token"], ts=time.time())
        return self._token["valor"]

    def _req(self, metodo, ruta, **kw):
        return self.http.request(metodo, f"https://www.zohoapis.{self._dom()}/crm/v6{ruta}",
                                 headers={"Authorization": f"Zoho-oauthtoken {self._access()}"}, timeout=20, **kw)

    def listar_productos(self):
        r = self._seguro(self._req, "GET", "/Products", params={"fields": ",".join(["Product_Name", "Unit_Price", "Description", "Product_Category"] + list((self.campos.get("catalogo") or {}).values()))})
        if not self._ok(r, "la lectura de productos"):
            return []
        items = []
        for p in r.json().get("data") or []:
            if p.get("Unit_Price") is None:
                continue
            item = {"external_crm_id": p["id"], "name_es": p.get("Product_Name"), "list_price": float(p["Unit_Price"]),
                    "category": p.get("Product_Category"), "media": []}
            for clave, api in (self.campos.get("catalogo") or {}).items():
                if p.get(api) not in (None, ""):
                    item[clave] = p[api]
            items.append(item)
        return items

    def sincronizar_lead(self, ficha):
        return self._seguro(self._sincronizar, ficha)

    def _sincronizar(self, ficha):
        nombre = (ficha.get("nombre") or "").split(" ", 1)
        estados = {**ESTADOS, **(self.campos.get("estados") or {})}
        datos = {"First_Name": nombre[0] if len(nombre) > 1 else None, "Last_Name": nombre[-1] or "Lead", "Phone": ficha.get("telefono"),
                 "Mobile": ficha.get("telefono"), "Company": ficha.get("empresa") or "Individual", "Lead_Source": ficha.get("canal"),
                 "Lead_Status": estados.get(ficha.get("etapa")), "Description": ficha.get("descripcion"),
                 **{api: ficha.get(c) for c, api in (self.campos.get("lead") or {}).items() if ficha.get(c) is not None}}
        datos = {k: v for k, v in datos.items() if v not in (None, "")}
        r = self._req("POST", "/Leads/upsert", json={"data": [datos], "duplicate_check_fields": ["Phone"]})
        if not self._ok(r, "el lead"):
            return None
        return ((r.json().get("data") or [{}])[0].get("details") or {}).get("id")

    def registrar_cita(self, crm_id, inicio, minutos, asunto, descripcion="", ubicacion="", cita_id=None):
        fin = inicio.timestamp() + minutos * 60
        datos = {"Event_Title": asunto, "Start_DateTime": inicio.isoformat(timespec="seconds"),
                 "End_DateTime": datetime.fromtimestamp(fin, inicio.tzinfo).isoformat(timespec="seconds"),
                 "Description": descripcion, "Venue": ubicacion, "What_Id": {"id": crm_id}, "$se_module": "Leads"}
        r = self._req("PUT", f"/Events/{cita_id}", json={"data": [datos]}) if cita_id else self._req("POST", "/Events", json={"data": [datos]})
        if not self._ok(r, "el evento"):
            return None
        return cita_id or ((r.json().get("data") or [{}])[0].get("details") or {}).get("id")

    def marcar_asistencia(self, cita_id, asistio, nota=""):
        r = self._req("PUT", f"/Events/{cita_id}", json={"data": [{"Description": (nota or "") + (" [ATTENDED]" if asistio else " [NO-SHOW]")}]})
        return cita_id if self._ok(r, "la asistencia") else None

    def registrar_nota(self, crm_id, asunto, cuerpo):
        r = self._req("POST", "/Notes", json={"data": [{"Note_Title": asunto, "Note_Content": cuerpo, "Parent_Id": {"module": {"api_name": "Leads"}, "id": crm_id}}]})
        return ((r.json().get("data") or [{}])[0].get("details") or {}).get("id") if self._ok(r, "la nota") else None
