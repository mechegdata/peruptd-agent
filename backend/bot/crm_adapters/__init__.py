"""Adaptadores multi-CRM bidireccionales. adaptador(tenant) devuelve el que corresponde a tenants.crm_type."""
from bot.crm_adapters import mapeo
from bot.crm_adapters.base import AdaptadorCRM


def adaptador(tenant, http=None):
    tipo = (tenant or {}).get("crm_type") or "peruptd_native"
    cred = (tenant or {}).get("crm_credentials_json") or {}
    campos = mapeo.para_adaptador(tenant or {})       # estándar del CRM + crm_field_mapping_json del cliente
    if tipo == "salesforce":
        from bot.crm_adapters.salesforce import SalesforceCRMAdapter as Clase
    elif tipo == "hubspot":
        from bot.crm_adapters.hubspot import HubSpotCRMAdapter as Clase
    elif tipo == "pipedrive":
        from bot.crm_adapters.pipedrive import PipedriveCRMAdapter as Clase
    elif tipo == "zoho":
        from bot.crm_adapters.zoho import ZohoCRMAdapter as Clase
    else:
        from bot.crm_adapters.nativo import PeruPTDNativeCRMAdapter as Clase
    return Clase(cred, campos, http)


__all__ = ["AdaptadorCRM", "adaptador"]
