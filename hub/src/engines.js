// ===== Layer 2 · Deterministic engines (catalog, budget/financing, 3-strike objections, agenda, media) =====
// ===== Layer 3 · Bilingual composer. No number in a reply is invented: everything comes from the catalog item. =====
const Engines = (() => {
  const money = (n, lang) => (lang === "es" ? "US$" : "$") + Math.round(n).toLocaleString("en-US");
  const L = (lang, en, es) => (lang === "es" ? es : en);

  function annuity(principal, annualPct, months) {
    if (!annualPct) return principal / months;
    const r = annualPct / 100 / 12;
    return (principal * r * Math.pow(1 + r, months)) / (Math.pow(1 + r, months) - 1);
  }

  // ---------- budget & financing ----------
  function budgetEngine(item, budget, payType, lang) {
    const cash = item.cash_price, list = item.list_price;
    const months = Math.max(1, Math.round(item.max_term_years * 12));
    if (budget == null) {
      if (payType !== "FINANCING") return null;
      const down = list * (item.rec_down_pct || 0) / 100;
      const m = annuity(list - down, item.annual_rate_pct, months);
      return { rule: "financing_plan", text: L(lang,
        `Payment plan: ${item.rec_down_pct}% down (${money(down, lang)}) and ~${money(m, lang)}/mo for ${months} months${item.annual_rate_pct ? ` (${item.annual_rate_pct}% APR est.)` : " at 0%"}.`,
        `Plan de pagos: ${item.rec_down_pct}% de inicial (${money(down, lang)}) y ~${money(m, lang)}/mes por ${months} meses${item.annual_rate_pct ? ` (TEA ref. ${item.annual_rate_pct}%)` : " sin intereses"}.`),
        calc: { down, monthly: Math.round(m), months } };
    }
    const gap = (cash - budget) / cash;
    if (gap <= 0) return { rule: "≥ cash price", text: L(lang, `Your ${money(budget, lang)} covers the cash price (${money(cash, lang)}) ✅ ${item.promo.en}.`, `Con ${money(budget, lang)} cubres el precio al contado (${money(cash, lang)}) ✅ ${item.promo.es}.`) };
    if (gap <= 0.08) return { rule: `${Math.round(gap * 100)}% below cash (≤ 8%)`, text: L(lang,
      `You're only ${Math.round(gap * 100)}% away from the cash price (${money(cash, lang)}) — that's close enough to talk it over in person 🤝`,
      `Estás a solo ${Math.round(gap * 100)}% del precio al contado (${money(cash, lang)}): eso se conversa en la reunión 🤝`) };
    if (gap <= 0.2) {
      const diff = cash - budget;
      return { rule: `${Math.round(gap * 100)}% below cash (8–20%)`, text: L(lang,
        `You can pay ${money(budget, lang)} now and cover the remaining ${money(diff, lang)} in 12 short installments of ~${money(diff / 12, lang)}.`,
        `Puedes dar ${money(budget, lang)} ahora y cubrir los ${money(diff, lang)} restantes en 12 cuotas cortas de ~${money(diff / 12, lang)}.`) };
    }
    const minDown = list * item.min_down_pct / 100;
    if (budget >= minDown) {
      const loan = list - budget, m = annuity(loan, item.annual_rate_pct, months);
      return { rule: `down payment ${Math.round((budget / list) * 100)}% ≥ ${item.min_down_pct}% min`, text: L(lang,
        `With ${money(budget, lang)} down (${Math.round((budget / list) * 100)}%), you'd finance ${money(loan, lang)}: ~${money(m, lang)}/mo over ${item.max_term_years} years (${item.annual_rate_pct}% APR est.).`,
        `Con ${money(budget, lang)} de inicial (${Math.round((budget / list) * 100)}%), financias ${money(loan, lang)}: ~${money(m, lang)}/mes a ${item.max_term_years} años (TEA ref. ${item.annual_rate_pct}%).`),
        calc: { down: budget, loan, monthly: Math.round(m), months } };
    }
    return { rule: `below ${item.min_down_pct}% minimum down`, text: L(lang,
      `The minimum down payment is ${item.min_down_pct}% (${money(minDown, lang)}). We can plan how to get there, or look at a lower-priced option.`,
      `La inicial mínima es ${item.min_down_pct}% (${money(minDown, lang)}). Podemos ver cómo llegar o revisar una opción más económica.`) };
  }

  // ---------- 3-strike objection ladder ----------
  function objectionEngine(item, strike, lang, ind) {
    if (strike === 1) return { strike, alert: L(lang, `Price objection 1/3 handled (${item.name.en}) — FYI`, `Objeción de precio 1/3 atendida (${item.name.es}) — para tu información`), media: "PRICE_OBJECTION", text: L(lang,
      `Totally fair to compare 🙂 ${item.value.en}.`, `Es normal comparar 🙂 ${item.value.es}.`) };
    if (strike === 2) return { strike, alert: L(lang, "Price objection 2/3 — good time to call this lead", "Objeción de precio 2/3 — buen momento para llamarle"), text: L(lang,
      `No pressure at all — come see it in person, zero commitment. Most people decide once they see it.`,
      `Sin compromiso: ven a verlo en persona. La mayoría decide recién cuando lo ve.`) };
    return { strike: 3, alert: L(lang, `URGENT: price objection 3/3 — escalated to ${ind.advisor}`, `URGENTE: objeción de precio 3/3 — escalado a ${ind.advisor}`), text: L(lang,
      `I understand. I've asked ${ind.advisor} to personally review options for you — they'll reach out today.`,
      `Te entiendo. Le pedí a ${ind.advisor} que revise personalmente opciones para ti; te escribe hoy.`) };
  }

  // ---------- agenda (fake but realistic busy calendar) ----------
  const BUSY = new Set(["+1|19:00", "+2|10:00"]);
  function dayOffset(rel) {
    const now = new Date();
    if (rel === "TOMORROW") return 1;
    if (rel === "TODAY") return 0;
    if (rel === "THIS_SATURDAY") return ((6 - now.getDay() + 7) % 7) || 7;
    if (rel === "THIS_SUNDAY") return ((7 - now.getDay()) % 7) || 7;
    if (rel === "MONDAY") return ((8 - now.getDay()) % 7) || 7;
    return 1;
  }
  const toMin = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; };
  const toHHMM = (min) => `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;

  function slotLabel(slot, lang) {
    const d = new Date(); d.setDate(d.getDate() + slot.off);
    const day = d.toLocaleDateString(lang === "es" ? "es-PE" : "en-US", { weekday: "short", day: "numeric", month: "short" });
    const [h, m] = slot.time.split(":").map(Number);
    const t = new Date(2000, 0, 1, h, m).toLocaleTimeString(lang === "es" ? "es-PE" : "en-US", { hour: "numeric", minute: "2-digit" });
    const rel = slot.off === 1 ? L(lang, "Tomorrow", "Mañana") : day.charAt(0).toUpperCase() + day.slice(1);
    return `${rel} · ${t}`;
  }

  function agendaEngine(ent, lang) {
    const off = dayOffset(ent.proposed_date_relative);
    const earliest = ent.work_end_constraint ? toMin(ent.work_end_constraint) + 30 : 9 * 60;
    const want = ent.proposed_time ? Math.max(toMin(ent.proposed_time), earliest) : Math.max(earliest, 10 * 60);
    const slots = [], skipped = [];
    for (let t = want; slots.length < 2 && t <= 20 * 60; t += 30) {
      const s = { off, time: toHHMM(t) };
      if (BUSY.has(`+${off}|${s.time}`)) { skipped.push(s.time); continue; }
      slots.push(s);
    }
    const alt = { off: off + 1, time: toHHMM(Math.max(want, 10 * 60)) };
    if (BUSY.has(`+${alt.off}|${alt.time}`)) alt.time = toHHMM(toMin(alt.time) + 60);
    slots.push(alt);
    return { slots, skipped, earliest: toHHMM(earliest) };
  }

  // ---------- media (max 2, never repeated) ----------
  function mediaEngine(item, triggers, sentIds) {
    const picked = [];
    for (const trig of triggers) {
      for (const m of item.media) {
        if (picked.length >= 2) break;
        if (m.trigger === trig && !sentIds.includes(m.id) && !picked.includes(m)) { picked.push(m); break; }
      }
    }
    return picked;
  }

  // ---------- pipeline ----------
  function run(nlu, ctx) {
    const { lead, industry: ind, lang } = ctx;
    const ent = nlu.extracted_entities, intents = [nlu.primary_intent, ...nlu.secondary_intents];
    const has = (i) => intents.some((x) => x.includes(i));
    const item = ind.items.find((i) => i.id === (ent.catalog_item_id || lead.interested_catalog_item_id)) || ind.items[0];
    const trace = [], parts = [], triggers = [], crm = {}, alerts = [];
    let slots = null, booked = null;
    lead.interested_catalog_item_id = item.id;
    crm.item = item.name[lang];

    if (has("NOT_INTERESTED")) {
      trace.push(["Courtesy", L(lang, "closes politely, stops follow-up", "cierra con cortesía, detiene el seguimiento")]);
      lead.stage = "lost";
      return { text: L(lang, "No problem at all, thanks for your time! If anything changes, I'm here 🙌", "¡Sin problema, gracias por tu tiempo! Si algo cambia, aquí estoy 🙌"), media: [], trace, crm: { stage: "lost" }, alerts };
    }

    if (has("SLOT_SELECTION") && lead.offered_slots && ent.selected_slot_index) {
      const s = lead.offered_slots[ent.selected_slot_index - 1];
      if (s) {
        booked = { ...s, label: slotLabel(s, lang) };
        lead.appointment = booked; lead.stage = "booked"; lead.offered_slots = null;
        trace.push(["Agenda", L(lang, `slot ${ent.selected_slot_index} free → event created`, `opción ${ent.selected_slot_index} libre → evento creado`)]);
        parts.push(L(lang, `Booked! ✅ Your ${ind.eventWord.en.toLowerCase()}: ${booked.label}\n📍 ${ind.location.en} — ${ind.mapsUrl}\nI'll confirm with you 24h before.`,
          `¡Listo! ✅ Agendé tu ${ind.eventWord.es.toLowerCase()}: ${booked.label}\n📍 ${ind.location.es} — ${ind.mapsUrl}\nTe confirmo 24 h antes.`));
        triggers.push("LOCATION_FACADE");
        crm.stage = "booked"; crm.appointment = booked.label;
        alerts.push(L(lang, `New ${ind.eventWord.en.toLowerCase()}: ${booked.label}`, `Nueva ${ind.eventWord.es.toLowerCase()}: ${booked.label}`));
      }
    }

    if (!booked && (has("GREETING") || has("PRICE") || has("CASH") || has("GENERAL_INFO") || !lead.greeted)) {
      const hi = !lead.greeted ? L(lang, `Hi! I'm ${ind.botName.en} from ${ind.company} 👋 `, `¡Hola! Soy ${ind.botName.es} de ${ind.company} 👋 `) : "";
      lead.greeted = true;
      const specs = Object.entries(item.specs[lang]).slice(0, 4).map(([k, v]) => `${k}: ${v}`).join(" · ");
      let price = "";
      if (has("PRICE") || has("CASH")) price = has("CASH")
        ? L(lang, ` Cash price: ${money(item.cash_price, lang)} (list ${money(item.list_price, lang)}).`, ` Al contado: ${money(item.cash_price, lang)} (precio de lista ${money(item.list_price, lang)}).`)
        : L(lang, ` It's ${money(item.list_price, lang)}, or ${money(item.cash_price, lang)} paying cash.`, ` Cuesta ${money(item.list_price, lang)}, o ${money(item.cash_price, lang)} al contado.`);
      parts.push(`${hi}*${item.name[lang]}* — ${specs}.${price}`);
      trace.push(["Catalog", `${item.external[ctx.crmKey]} · ${L(lang, "list", "lista")} ${money(item.list_price, lang)} · ${L(lang, "cash", "contado")} ${money(item.cash_price, lang)}`]);
      if (!lead.sent_media_ids.length) triggers.push("FIRST_INFO");
    }

    if (ent.price_objection) {
      lead.price_objection_count = Math.min(3, (lead.price_objection_count || 0) + 1);
      const o = objectionEngine(item, lead.price_objection_count, lang, ind);
      parts.push(o.text);
      if (o.media) triggers.unshift(o.media);
      alerts.push(o.alert);
      trace.push([`Objection ${o.strike}/3`, o.alert]);
      crm.objections = lead.price_objection_count;
    }

    if (ent.budget_amount != null || ent.payment_type === "FINANCING") {
      const b = budgetEngine(item, ent.budget_amount ?? null, ent.payment_type, lang);
      if (b) { parts.push(b.text); trace.push(["Budget", b.rule + (b.calc && b.calc.monthly ? ` → M = ${money(b.calc.monthly, lang)}/mo` : "")]); }
      if (ent.budget_amount != null) { lead.stated_budget = ent.budget_amount; crm.budget = money(ent.budget_amount, lang); }
    }
    if (ent.payment_type) { lead.payment_method = ent.payment_type; crm.payment = ent.payment_type === "CASH" ? L(lang, "Cash", "Contado") : L(lang, "Financing", "Financiamiento"); }
    if (ent.insurance && item.insurance) { parts.push(item.insurance[lang] + "."); trace.push(["Insurance", ent.insurance]); crm.payment = (crm.payment ? crm.payment + " / " : "") + "PPO"; }

    if (has("SPECS_AND_PLANS")) { triggers.push("SPECS_PDF"); trace.push(["Media", "SPECS_PDF"]); parts.push(L(lang, "Sending you the document 👇", "Te envío el documento 👇")); }
    if (has("VIDEO_TOUR")) { triggers.push("VIDEO_TOUR"); parts.push(L(lang, "Here's the video 🎬", "Aquí tienes el video 🎬")); }
    if (has("LOCATION")) { triggers.push("LOCATION_FACADE"); parts.push(L(lang, `📍 ${ind.location.en} — ${ind.mapsUrl}`, `📍 ${ind.location.es} — ${ind.mapsUrl}`)); }

    if (!booked && has("SCHEDULE")) {
      const a = agendaEngine(ent, lang);
      lead.offered_slots = a.slots;
      slots = a.slots.map((s) => slotLabel(s, lang));
      const nums = ["1️⃣", "2️⃣", "3️⃣"];
      parts.push(L(lang, `Checked the live calendar${ent.work_end_constraint ? ` (you're off at ${ent.work_end_constraint}, so from ${a.earliest})` : ""}:\n`, `Revisé la agenda real${ent.work_end_constraint ? ` (sales del trabajo a las ${ent.work_end_constraint}, así que desde las ${a.earliest})` : ""}:\n`)
        + slots.map((s, i) => `${nums[i]} ${s}`).join("\n") + L(lang, "\nReply 1, 2 or 3 👍", "\nResponde 1, 2 o 3 👍"));
      trace.push(["Agenda", `${L(lang, "free slots", "turnos libres")} ≥ ${a.earliest}${a.skipped.length ? ` · ${L(lang, "skipped busy", "ocupado")} ${a.skipped.join(", ")}` : ""}`]);
      if (lead.stage === "new") lead.stage = "qualified";
    }

    if (lead.stage === "new" && (lead.payment_method || lead.stated_budget)) lead.stage = "qualified";
    if (!parts.length) {
      parts.push(L(lang, `Happy to help! ${item.promo.en}. Want me to send the details or book a visit?`, `¡Con gusto! ${item.promo.es}. ¿Te envío los detalles o agendamos una visita?`));
      trace.push(["AI fallback", L(lang, "guardrailed: catalog data only + forbidden phrases filter", "con guardas: solo datos del catálogo + filtro de frases prohibidas")]);
    }

    const media = mediaEngine(item, triggers, lead.sent_media_ids);
    media.forEach((m) => lead.sent_media_ids.push(m.id));
    if (media.length) trace.push(["Media", media.map((m) => `${m.trigger}:${m.id}`).join(" + ") + L(lang, " (max 2, no repeats)", " (máx. 2, sin repetir)")]);
    crm.stage = lead.stage; crm.language = lang.toUpperCase();
    crm.media = lead.sent_media_ids.length;
    return { text: parts.join("\n\n"), media, trace, crm, alerts, slots, booked };
  }

  return { run, annuity, budgetEngine, money };
})();
