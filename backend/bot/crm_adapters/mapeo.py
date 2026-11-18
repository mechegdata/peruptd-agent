"""Mapeo flexible de objetos y campos del CRM externo de cada cliente (tenants.crm_field_mapping_json).

Vacío = objetos estándar de cada CRM (POR_DEFECTO). Lo que el cliente ponga se mezcla encima, así que basta con indicar
solo lo distinto. Formato:
  {"catalog": {"object": "Product2", "active_field": "IsActive",
               "fields": {"name_es": "Name", "list_price": "PricebookEntry.UnitPrice", "cash_price": "Cash_Price__c", ...}},
   "lead":    {"object": "Lead", "fields": {"presupuesto": "Initial_Budget__c", "pago": "Payment_Method__c", ...}},
   "event_attendance": "Attendance__c"}
Claves de catálogo que entiende el motor: CAMPOS_CATALOGO. Claves de lead que escribe el agente: CAMPOS_LEAD.
Compatibilidad: el formato anterior tenants.crm_field_map {"catalogo": {...}, "lead": {...}} se sigue leyendo."""
import copy
import re

CAMPOS_CATALOGO = ("name_es", "name_en", "list_price", "cash_price", "category", "keywords", "currency", "min_down_payment_pct",
                   "recommended_down_payment_pct", "annual_rate_pct", "max_term_years", "promo_bonus_es", "promo_bonus_en",
                   "value_comparison_es", "value_comparison_en", "insurance_es", "insurance_en", "conditions_es", "conditions_en",
                   "qualification_mode", "location_address", "google_maps_url", "status")
CAMPOS_LEAD = ("presupuesto", "pago", "objeciones", "idioma", "producto", "inicial", "cuota", "etapa")
API = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}(\.[A-Za-z][A-Za-z0-9_]{0,79})?$")

POR_DEFECTO = {
    "salesforce": {"catalog": {"object": "Product2", "active_field": "IsActive",
                               "fields": {"name_es": "Name", "list_price": "PricebookEntry.UnitPrice", "category": "Family",
                                          "keywords": "ProductCode"}},
                   "lead": {"object": "Lead", "fields": {}}, "event_attendance": None},
    "hubspot": {"catalog": {"object": "products", "fields": {"name_es": "name", "list_price": "price", "category": "hs_product_type"}},
                "lead": {"object": "contacts", "fields": {}}},
    "pipedrive": {"catalog": {"object": "products", "fields": {"name_es": "name", "list_price": "prices.price", "category": "category"}},
                  "lead": {"object": "persons", "fields": {}}},
    "zoho": {"catalog": {"object": "Products", "fields": {"name_es": "Product_Name", "list_price": "Unit_Price",
                                                           "category": "Product_Category"}},
             "lead": {"object": "Leads", "fields": {}}},
    "peruptd_native": {"catalog": {"object": "catalog_items", "fields": {}}, "lead": {"object": "leads", "fields": {}}},
}
_ESTANDAR = {t: set(m["catalog"]["fields"]) for t, m in POR_DEFECTO.items()}


def _mezclar(base, extra):
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _mezclar(base[k], v)
        else:
            base[k] = v
    return base


def efectivo(tenant):
    """Mapeo final del tenant: estándar del CRM <- crm_field_map (formato antiguo) <- crm_field_mapping_json."""
    tipo = (tenant or {}).get("crm_type") or "peruptd_native"
    m = copy.deepcopy(POR_DEFECTO.get(tipo, POR_DEFECTO["peruptd_native"]))
    viejo = (tenant or {}).get("crm_field_map") or {}
    if viejo:
        _mezclar(m, {"catalog": {"fields": viejo.get("catalogo") or {}}, "lead": {"fields": viejo.get("lead") or {}},
                     **({"event_attendance": viejo["event_attendance"]} if viejo.get("event_attendance") else {}),
                     **{k: v for k, v in viejo.items() if k not in ("catalogo", "lead", "event_attendance")}})
    return _mezclar(m, (tenant or {}).get("crm_field_mapping_json") or {})


def para_adaptador(tenant):
    """Lo que reciben los adaptadores en self.campos: el mapeo completo + los atajos 'catalogo' (solo campos propios,
    los estándar ya los lee cada adaptador) y 'lead' que usaban antes."""
    m = efectivo(tenant)
    tipo = (tenant or {}).get("crm_type") or "peruptd_native"
    propios = {k: v for k, v in m["catalog"]["fields"].items()
               if v and (k not in _ESTANDAR.get(tipo, set()) or v != POR_DEFECTO.get(tipo, {}).get("catalog", {}).get("fields", {}).get(k))}
    return {**{k: v for k, v in m.items() if k not in ("catalog", "lead")}, "mapeo": m,
            "catalogo": propios, "lead": {k: v for k, v in m["lead"]["fields"].items() if v}}


def validar(mapeo):
    """(mapeo_limpio, error). Solo nombres de API válidos (sin espacios ni SOQL/SQL): evita inyección en las consultas."""
    if not isinstance(mapeo, dict):
        return None, "crm_field_mapping debe ser un objeto"
    limpio = {}
    for seccion, claves in (("catalog", CAMPOS_CATALOGO), ("lead", CAMPOS_LEAD)):
        s = mapeo.get(seccion)
        if s is None:
            continue
        if not isinstance(s, dict):
            return None, f"{seccion} debe ser un objeto"
        out = {}
        for k in ("object", "active_field"):
            if s.get(k):
                if not API.match(str(s[k])) or "." in str(s[k]):
                    return None, f"{seccion}.{k}: nombre de API no válido ({s[k]})"
                out[k] = str(s[k])
        campos = {}
        for clave, api in (s.get("fields") or {}).items():
            if clave not in claves:
                return None, f"{seccion}.fields: clave desconocida '{clave}' (válidas: {', '.join(claves)})"
            if api in (None, ""):
                campos[clave] = None
            elif not API.match(str(api)):
                return None, f"{seccion}.fields.{clave}: nombre de API no válido ({api})"
            else:
                campos[clave] = str(api)
        if campos:
            out["fields"] = campos
        limpio[seccion] = out
    if mapeo.get("event_attendance") not in (None, ""):
        if not API.match(str(mapeo["event_attendance"])):
            return None, "event_attendance: nombre de API no válido"
        limpio["event_attendance"] = str(mapeo["event_attendance"])
    return limpio, None
