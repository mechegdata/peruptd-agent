"""Motor multimedia: elige hasta 2 archivos del catálogo según el momento de la conversación (trigger_moment), sin
repetir nada que el lead ya recibió (lead.sent_media_ids). Controla costo y evita saturar al cliente."""
MAX_POR_TURNO = 2


def elegir(item, triggers, enviados, maximo=MAX_POR_TURNO):
    enviados = {str(x) for x in (enviados or [])}
    elegidos = []
    for grupo in triggers:
        if len(elegidos) >= maximo:
            break
        for trig in grupo.split("|"):          # "LOCATION_MAP|LOCATION_FACADE": el primero que exista
            m = next((m for m in sorted(item.get("media") or [], key=lambda x: x.get("sort_order") or 0)
                      if m.get("trigger_moment") == trig and str(m.get("id")) not in enviados and m not in elegidos), None)
            if m:
                elegidos.append(m)
                break
    return elegidos
