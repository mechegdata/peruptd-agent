"""CRM -> Supabase: copia productos, precios y archivos del CRM del cliente a catalog_items / catalog_media.
Los archivos privados del CRM (p. ej. ContentVersion de Salesforce) se descargan y se suben al bucket público
'catalogo' de Supabase Storage, porque WhatsApp/Twilio necesitan una URL pública para enviarlos.
Lo dispara /catalogo/sincronizar (Cloud Scheduler o un webhook del CRM cuando cambia un producto)."""
import hashlib
import mimetypes

from bot import catalogo, db
from bot.config import TENANT_ID
from bot.crm_adapters import adaptador
from bot.tenant import actual as tenant_actual

BUCKET = "catalogo"
_CAMPOS = {"external_crm_id", "name_es", "name_en", "keywords", "category", "status", "specs_json", "list_price", "cash_price",
           "currency", "min_down_payment_pct", "recommended_down_payment_pct", "annual_rate_pct", "max_term_years",
           "promo_bonus_es", "promo_bonus_en", "value_comparison_es", "value_comparison_en", "insurance_es", "insurance_en", "location_address", "google_maps_url"}


def _subir(contenido, nombre):
    ruta = f"{TENANT_ID}/{hashlib.sha1(contenido).hexdigest()[:16]}-{nombre}"
    tipo = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
    try:
        db.supabase.storage.from_(BUCKET).upload(ruta, contenido, {"content-type": tipo, "upsert": "true"})
    except Exception as e:
        if "Duplicate" not in str(e) and "already exists" not in str(e):
            raise
    return db.supabase.storage.from_(BUCKET).get_public_url(ruta)


def sincronizar(adapt=None):
    """Devuelve un resumen {'items': n, 'media': n, 'errores': [...]}."""
    resumen = {"items": 0, "media": 0, "errores": []}
    if not db.supabase:
        resumen["errores"].append("Supabase no configurado")
        return resumen
    adapt = adapt or adaptador(tenant_actual())
    for prod in adapt.listar_productos() or []:
        try:
            fila = {k: v for k, v in prod.items() if k in _CAMPOS}
            fila.update(tenant_id=TENANT_ID, name_es=fila.get("name_es") or "Producto")
            guardado = db.supabase.table("catalog_items").upsert(fila, on_conflict="tenant_id,external_crm_id").execute().data[0]
            resumen["items"] += 1
            for i, m in enumerate(prod.get("media") or []):
                url = m.get("file_url")
                if not url and m.get("descargar"):
                    contenido = m["descargar"]()
                    url = _subir(contenido, m.get("nombre_archivo") or f"archivo-{i}") if contenido else None
                if not url:
                    continue
                existe = db.supabase.table("catalog_media").select("id").eq("catalog_item_id", guardado["id"]).eq("file_url", url).limit(1).execute().data
                if not existe:
                    db.supabase.table("catalog_media").insert({
                        "catalog_item_id": guardado["id"], "tenant_id": TENANT_ID, "file_url": url, "media_type": m["media_type"],
                        "trigger_moment": m["trigger_moment"], "caption_es": m.get("caption_es"), "caption_en": m.get("caption_en"),
                        "sort_order": i}).execute()
                    resumen["media"] += 1
        except Exception as e:
            resumen["errores"].append(f"{prod.get('name_es')}: {str(e)[:150]}")
    catalogo.limpiar_cache()
    return resumen
