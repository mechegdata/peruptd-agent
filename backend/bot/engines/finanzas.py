"""Motor de presupuesto y financiamiento (reglas del documento PeruPTD):
  presupuesto >= contado            -> viable + bono activo
  hasta 8 % por debajo del contado  -> cerca: se negocia en la cita
  entre 8 % y 20 % por debajo       -> cubrir la diferencia con financiamiento corto (12 cuotas)
  menor, pero >= inicial mínima     -> se toma como inicial y se calcula la cuota con la fórmula de anualidad
  menor que la inicial mínima       -> se indica la inicial mínima y se sugiere otra opción
M = P · r(1+r)^n / ((1+r)^n − 1), con r = tasa anual / 12 y n = meses."""
from bot.engines.textos import L, campo, dinero


def cuota_mensual(principal, tasa_anual_pct, meses):
    meses = max(1, int(round(meses)))
    if not tasa_anual_pct:
        return principal / meses
    r = tasa_anual_pct / 100 / 12
    return principal * r * (1 + r) ** meses / ((1 + r) ** meses - 1)


def evaluar(item, presupuesto, tipo_pago, idioma):
    """Devuelve {'regla', 'texto', 'calculo'} o None si no hay nada que calcular."""
    mon = item.get("currency") or "USD"
    lista = float(item["list_price"])
    contado = float(item.get("cash_price") or lista)
    meses = max(1, round(float(item.get("max_term_years") or 1) * 12))
    tasa = float(item.get("annual_rate_pct") or 0)
    d = lambda n: dinero(n, idioma, mon)  # noqa: E731
    if presupuesto is None:
        if tipo_pago != "FINANCING":
            return None
        rec = float(item.get("recommended_down_payment_pct") or 0)
        inicial = lista * rec / 100
        m = cuota_mensual(lista - inicial, tasa, meses)
        sufijo_en = f" ({tasa}% APR est.)" if tasa else " at 0%"
        sufijo_es = f" (TEA ref. {tasa}%)" if tasa else " sin intereses"
        return {"regla": "plan_financiamiento", "calculo": {"inicial": round(inicial), "cuota": round(m), "meses": meses},
                "texto": L(idioma, f"Payment plan: {rec:g}% down ({d(inicial)}) and ~{d(m)}/mo for {meses} months{sufijo_en}.",
                           f"Plan de pagos: {rec:g}% de inicial ({d(inicial)}) y ~{d(m)}/mes por {meses} meses{sufijo_es}.")}
    brecha = (contado - presupuesto) / contado
    if brecha <= 0:
        return {"regla": "cubre_contado", "calculo": {}, "texto": L(idioma,
                f"Your {d(presupuesto)} covers the cash price ({d(contado)}) ✅ {campo(item, 'promo_bonus', 'en')}".strip(),
                f"Con {d(presupuesto)} cubres el precio al contado ({d(contado)}) ✅ {campo(item, 'promo_bonus', 'es')}".strip())}
    pct = round(brecha * 100)
    if brecha <= 0.08:
        return {"regla": f"cerca_{pct}pct", "calculo": {}, "texto": L(idioma,
                f"You're only {pct}% away from the cash price ({d(contado)}) — close enough to talk it over in person 🤝",
                f"Estás a solo {pct}% del precio al contado ({d(contado)}): eso se conversa en la reunión 🤝")}
    if brecha <= 0.20:
        dif = contado - presupuesto
        return {"regla": f"diferencia_corta_{pct}pct", "calculo": {"diferencia": round(dif), "cuota": round(dif / 12), "meses": 12},
                "texto": L(idioma, f"You can pay {d(presupuesto)} now and cover the remaining {d(dif)} in 12 short installments of ~{d(dif / 12)}.",
                           f"Puedes dar {d(presupuesto)} ahora y cubrir los {d(dif)} restantes en 12 cuotas cortas de ~{d(dif / 12)}.")}
    minimo = lista * float(item.get("min_down_payment_pct") or 0) / 100
    if presupuesto >= minimo:
        prestamo = lista - presupuesto
        m = cuota_mensual(prestamo, tasa, meses)
        pct_ini = round(presupuesto / lista * 100)
        anios = f"{float(item.get('max_term_years') or 1):g}"
        return {"regla": f"inicial_{pct_ini}pct", "calculo": {"inicial": round(presupuesto), "prestamo": round(prestamo), "cuota": round(m), "meses": meses},
                "texto": L(idioma, f"With {d(presupuesto)} down ({pct_ini}%), you'd finance {d(prestamo)}: ~{d(m)}/mo over {anios} years ({tasa}% APR est.).",
                           f"Con {d(presupuesto)} de inicial ({pct_ini}%), financias {d(prestamo)}: ~{d(m)}/mes a {anios} años (TEA ref. {tasa}%).")}
    return {"regla": "bajo_inicial_minima", "calculo": {"inicial_minima": round(minimo)}, "texto": L(idioma,
            f"The minimum down payment is {float(item.get('min_down_payment_pct') or 0):g}% ({d(minimo)}). We can plan how to get there, or look at a lower-priced option.",
            f"La inicial mínima es {float(item.get('min_down_payment_pct') or 0):g}% ({d(minimo)}). Podemos ver cómo llegar o revisar una opción más económica.")}
