"""SalesforceCRMAdapter: catálogo desde Product2 + PricebookEntry + archivos (ContentDocumentLink / ContentVersion) y
escritura en Lead, Event y Task (reutiliza bot/integraciones/salesforce_sync.py: OAuth Client Credentials o JWT).
Mapeo de campos propios (tenants.crm_field_map):
  {"catalogo": {"cash_price": "Cash_Price__c", "min_down_payment_pct": "Min_Down__c", "value_comparison_es": "Value_ES__c"},
   "lead": {"pago": "Payment_Method__c", "presupuesto": "Initial_Budget__c", "objeciones": "Price_Objection_Count__c",
            "idioma": "Preferred_Language__c", "producto": "Interested_Product__c"},
   "event_attendance": "Attendance__c"}"""
from bot.crm_adapters.base import AdaptadorCRM, leyenda, tipo_por_nombre, trigger_por_nombre
from bot.integraciones import salesforce_sync as sf

_ESTANDAR = "SELECT Id, Name, Description, Family, ProductCode{extra}, (SELECT UnitPrice FROM PricebookEntries WHERE IsActive = true AND Pricebook2.IsStandard = true LIMIT 1) FROM Product2 WHERE IsActive = true ORDER BY Name LIMIT 200"


class SalesforceCRMAdapter(AdaptadorCRM):
    nombre = "salesforce"

    def listar_productos(self):
        extra = "".join(f", {c}" for c in sorted(set((self.campos.get("catalogo") or {}).values())))
        productos = sf.consultar(_ESTANDAR.format(extra=extra))
        if not productos:
            return []
        ids = "', '".join(sf.soql_texto(p["Id"]) for p in productos)
        enlaces = sf.consultar("SELECT LinkedEntityId, ContentDocument.Title, ContentDocument.FileExtension, "
                               f"ContentDocument.LatestPublishedVersionId FROM ContentDocumentLink WHERE LinkedEntityId IN ('{ids}')")
        archivos = {}
        for e in enlaces:
            doc = e.get("ContentDocument") or {}
            nombre = f"{doc.get('Title')}.{doc.get('FileExtension') or ''}"
            tipo = tipo_por_nombre(nombre)
            version = doc.get("LatestPublishedVersionId")
            archivos.setdefault(e["LinkedEntityId"], []).append({
                "external_id": version, "media_type": tipo, "trigger_moment": trigger_por_nombre(doc.get("Title"), tipo),
                "caption_es": leyenda(doc.get("Title")), "nombre_archivo": nombre,
                "descargar": (lambda v=version: self._descargar(v))})
        items = []
        for p in productos:
            precio = ((p.get("PricebookEntries") or {}).get("records") or [{}])[0].get("UnitPrice")
            if precio is None:
                continue
            item = {"external_crm_id": p["Id"], "name_es": p["Name"], "category": p.get("Family"), "list_price": precio,
                    "keywords": [w for w in (p.get("ProductCode") or "").lower().split(",") if w], "media": archivos.get(p["Id"], [])}
            for clave, api in (self.campos.get("catalogo") or {}).items():
                if p.get(api) is not None:
                    item[clave] = p[api]
            items.append(item)
        return items

    def _descargar(self, version_id):
        r = sf._api("GET", f"/sobjects/ContentVersion/{version_id}/VersionData")
        return r.content if self._ok(r, "la descarga del archivo") else None

    def sincronizar_lead(self, ficha):
        campos = {api: ficha.get(clave) for clave, api in (self.campos.get("lead") or {}).items() if ficha.get(clave) is not None}
        if ficha.get("etapa_crm"):
            campos["Status"] = ficha["etapa_crm"]
        campos["Description"] = ficha.get("descripcion")
        campos["LeadSource"] = ficha.get("canal")
        return sf.upsert_lead_from_chat(ficha.get("nombre"), ficha.get("telefono"), {k: v for k, v in campos.items() if v not in (None, "")},
                                        ficha.get("crm_id"), ficha.get("empresa") or "Individual")

    def registrar_cita(self, crm_id, inicio, minutos, asunto, descripcion="", ubicacion="", cita_id=None):
        return sf.create_salesforce_event(crm_id, inicio, minutos, asunto, descripcion, ubicacion, event_id=cita_id)

    def marcar_asistencia(self, cita_id, asistio, nota=""):
        return sf.update_event_attendance(cita_id, "Attended" if asistio else "No_Show", nota, self.campos.get("event_attendance"))

    def registrar_nota(self, crm_id, asunto, cuerpo):
        return sf.log_chat_summary_note(crm_id, asunto, cuerpo)
