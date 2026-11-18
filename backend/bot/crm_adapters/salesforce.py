"""SalesforceCRMAdapter: catálogo desde Product2 + PricebookEntry + archivos (ContentDocumentLink / ContentVersion) y
escritura en Lead, Event y Task (reutiliza bot/integraciones/salesforce_sync.py: OAuth Client Credentials o JWT).
Objetos y campos configurables por cliente (tenants.crm_field_mapping_json, ver crm_adapters/mapeo.py):
  {"catalog": {"object": "Product2", "fields": {"cash_price": "Cash_Price__c", "min_down_payment_pct": "Min_Down__c"}},
   "lead": {"fields": {"pago": "Payment_Method__c", "presupuesto": "Initial_Budget__c", "objeciones": "Price_Objection_Count__c"}},
   "event_attendance": "Attendance__c"}
Con "object" distinto de Product2 (p. ej. "Property__c") el catálogo se lee de ese objeto con los campos indicados
(name_es y list_price obligatorios); los archivos adjuntos se leen igual (ContentDocumentLink)."""
from bot.crm_adapters.base import AdaptadorCRM, leyenda, tipo_por_nombre, trigger_por_nombre
from bot.integraciones import salesforce_sync as sf

_ESTANDAR = "SELECT Id, Name, Description, Family, ProductCode{extra}, (SELECT UnitPrice FROM PricebookEntries WHERE IsActive = true AND Pricebook2.IsStandard = true LIMIT 1) FROM Product2 WHERE IsActive = true ORDER BY Name LIMIT 200"


class SalesforceCRMAdapter(AdaptadorCRM):
    nombre = "salesforce"

    def _cat(self):
        return ((self.campos.get("mapeo") or {}).get("catalog") or {})

    def _consulta_catalogo(self):
        cat = self._cat()
        objeto = cat.get("object") or "Product2"
        if objeto == "Product2":
            extra = "".join(f", {c}" for c in sorted(set((self.campos.get("catalogo") or {}).values())) if "." not in c)
            return _ESTANDAR.format(extra=extra), None
        campos = {k: v for k, v in (cat.get("fields") or {}).items() if v}
        if not campos.get("name_es") or not campos.get("list_price"):
            raise ValueError(f"mapeo de catálogo para {objeto}: faltan name_es y list_price")
        lista = ", ".join(["Id"] + sorted(set(campos.values()) - {"Id"}))
        filtro = f" WHERE {cat['active_field']} = true" if cat.get("active_field") else ""
        return f"SELECT {lista} FROM {objeto}{filtro} ORDER BY {campos['name_es']} LIMIT 200", campos

    @staticmethod
    def _leer(fila, api):
        for parte in api.split("."):
            fila = (fila or {}).get(parte) if isinstance(fila, dict) else None
        return fila

    def listar_productos(self):
        consulta, campos_propios = self._consulta_catalogo()
        productos = sf.consultar(consulta)
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
        if campos_propios:                      # objeto personalizado: todo sale del mapeo
            items = []
            for p in productos:
                item = {"external_crm_id": p["Id"], "media": archivos.get(p["Id"], [])}
                for clave, api in campos_propios.items():
                    v = self._leer(p, api)
                    if v is not None:
                        item[clave] = [w.strip() for w in str(v).lower().split(",") if w.strip()] if clave == "keywords" else v
                if item.get("name_es") and item.get("list_price") is not None:
                    items.append(item)
            return items
        for p in productos:
            precio = ((p.get("PricebookEntries") or {}).get("records") or [{}])[0].get("UnitPrice")
            if precio is None:
                continue
            item = {"external_crm_id": p["Id"], "name_es": p["Name"], "category": p.get("Family"), "list_price": precio,
                    "keywords": [w for w in (p.get("ProductCode") or "").lower().split(",") if w], "media": archivos.get(p["Id"], [])}
            for clave, api in (self.campos.get("catalogo") or {}).items():
                if "." not in api and p.get(api) is not None:
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
