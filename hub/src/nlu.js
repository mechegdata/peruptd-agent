// ===== Layer 1 · Semantic NLU (demo build): slang/typo lexicon + intent & entity extraction, ES/EN/Spanglish =====
const NLU = (() => {
  const strip = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const fmt = (n) => n.toLocaleString("en-US");

  function detectLanguage(text, previous) {
    const t = " " + strip(text).replace(/[^a-z0-9ñ' ]/g, " ") + " ";
    let es = 0, en = 0;
    for (const w of LEXICON.senales_idioma.es) if (t.includes(" " + strip(w) + " ")) es += 1;
    for (const w of LEXICON.senales_idioma.en) if (t.includes(" " + strip(w) + " ")) en += 1;
    for (const tok of t.trim().split(/\s+/)) {
      if (LEXICON.es[tok] && !LEXICON.en[tok]) es += 0.6;
      if (LEXICON.en[tok] && !LEXICON.es[tok]) en += 0.6;
    }
    if (/[ñ¿¡]|ción\b/.test(text)) es += 1;
    if (es === en) return previous || "es";
    return es > en ? "es" : "en";
  }

  // numbers like 25k, 25 mil, 2 lucas, $25,000, 2k
  function extractBudget(raw, slang) {
    const t = strip(raw);
    let m = t.match(/(\d+(?:[.,]\d+)?)\s*(lucas|luca)\b/);
    if (m) { slang.push(`${m[1]} ${m[2]} (${fmt(Math.round(parseFloat(m[1].replace(",", ".")) * 1000))})`); return Math.round(parseFloat(m[1].replace(",", ".")) * 1000); }
    m = t.match(/(\d+(?:[.,]\d+)?)\s*k\b/);
    if (m) { slang.push(`${m[1]}k (${fmt(Math.round(parseFloat(m[1]) * 1000))})`); return Math.round(parseFloat(m[1].replace(",", ".")) * 1000); }
    m = t.match(/(\d+(?:[.,]\d+)?)\s*mil\b/);
    if (m) return Math.round(parseFloat(m[1].replace(",", ".")) * 1000);
    m = t.match(/(?:\$|us\$|usd\s*)\s?(\d{1,3}(?:,\d{3})+|\d{3,})/);
    if (m) return parseInt(m[1].replace(/,/g, ""), 10);
    m = t.match(/\b(?:tengo|got|budget(?: is)?(?: like)?|presupuesto(?: de)?|cuento con)\s+(\d{3,})/);
    if (m) return parseInt(m[1], 10);
    return null;
  }

  function extractTime(raw, slang) {
    const t = strip(raw);
    let m = t.match(/(?:tipo|a las|como a las|round|around|at|@)\s*(\d{1,2})(?::(\d{2}))?\s*(y media|y cuarto|ish|pm|am|p\.m\.|de la tarde|de la noche)?/);
    if (!m) m = t.match(/\b(\d{1,2})(?::(\d{2}))?\s*(pm|am|ish|y media)\b/);
    if (!m) return null;
    let h = parseInt(m[1], 10), min = m[2] ? parseInt(m[2], 10) : 0;
    const suf = m[3] || "";
    if (suf === "y media") min = 30;
    if (suf === "y cuarto") min = 15;
    if (suf.includes("ish")) slang.push(`${m[1]}ish (≈ ${h}:00)`);
    if (suf.startsWith("am")) { /* keep */ } else if (h >= 1 && h <= 7) h += 12;
    else if (/pm|tarde|noche/.test(suf) && h < 12) h += 12;
    if (h > 23) return null;
    return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
  }

  function relativeDate(t) {
    if (/\b(manana|tomorrow)\b/.test(t)) return "TOMORROW";
    if (/\b(hoy|today|tonight|esta noche)\b/.test(t)) return "TODAY";
    if (/\b(sabado|saturday)\b/.test(t)) return /\bthis\b|\beste\b/.test(t) || true ? "THIS_SATURDAY" : "SATURDAY";
    if (/\b(domingo|sunday)\b/.test(t)) return "THIS_SUNDAY";
    if (/\b(lunes|monday)\b/.test(t)) return "MONDAY";
    return null;
  }

  function expand(raw, lang, slang) {
    const dict = LEXICON[lang];
    for (const [from, to] of Object.entries((LEXICON.frases || {})[lang] || {})) {
      const re = new RegExp(`\\b${from}\\b`, "gi");
      if (re.test(raw)) { raw = raw.replace(re, to); if (!/^(q tal|a cuanto sale)$/.test(from)) slang.push(`${from} (${to})`); }
    }
    const out = raw.replace(/[A-Za-zÁÉÍÓÚáéíóúñÑ0-9'/]+/g, (tok) => {
      const key = strip(tok);
      if (/^\d+k$/.test(key) || /^\d+$/.test(key)) return tok;
      const rep = dict[key];
      if (rep && strip(rep) !== key) { slang.push(`${tok} (${rep})`); return rep; }
      if (rep && rep !== tok && strip(rep) === key) return rep; // accent fix only
      return tok;
    });
    return out;
  }

  const INTENTS = [
    ["NOT_INTERESTED", /\b(no me interesa|ya no|not interested|no thanks|stop)\b/],
    ["SLOT_SELECTION", /^\s*(?:opcion |option |la |the )?(1|2|3|primera|segunda|tercera|first|second|third)(?: one| opcion| option)?\s*[.!]?\s*$/],
    ["RESCHEDULE", /\b(reprogram|cambiar la (cita|hora)|reschedule|move (my|the) (appointment|tour))/],
    ["GREETING", /^(hola|buenas|hey|hi|hello|buenos dias|buenas tardes)\b/],
    ["CASH_DISCOUNT", /\b(contado|cash|al contado|pago unico|paid in full)\b/],
    ["PRICE_INQUIRY", /\b(cuanto|precio|cuesta|sale|how much|price|pricing|cost|hm)\b/],
    ["OBJECTION_EXPENSIVE", /\b(caro|carisimo|expensive|too much|pricey|out of my budget|muy alto)\b/],
    ["FINANCING_CALCULATION", /\b(cuotas?|financ\w*|credito|inicial|payment plans?|monthly|down payment|\bdown\b|installments?|plazos?)\b/],
    ["BUDGET_STATEMENT", /\b(tengo|got|budget|presupuesto|cuento con|only have|solo tengo)\b/],
    ["INSURANCE_INQUIRY", /\b(seguro|insurance|ppo|hmo|delta dental|cigna|metlife)\b/],
    ["SPECS_AND_PLANS", /\b(planos?|floor ?plans?|pdf|ficha|brochure|specs?|guia|guide|sla|technical sheet|blueprints?)\b/],
    ["VIDEO_TOUR", /\b(video|recorrido|walkthrough|tour video|demo video)\b/],
    ["LOCATION_INQUIRY", /\b(donde|ubicacion|ubicados|direccion|where|located|location|address)\b/],
    ["SCHEDULE_REQUEST", /\b(ver|visita|visitar|cita|agendar|tour|visit|appointment|book|call|reunion|puedo el|free this|se podra)\b/],
    ["COURTESY_WAIT", /\b(lo pienso|te aviso|let me think|i'll let you know|despues te escribo)\b/]
  ];

  function normalize(raw, opts) {
    const t0 = performance.now();
    const items = (opts && opts.items) || [];
    const lang = detectLanguage(raw, opts && opts.previousLanguage);
    const slang = [];
    const budget = extractBudget(raw, slang);
    const time = extractTime(raw, slang);
    let clean = expand(raw, lang, slang).replace(/\s+/g, " ").replace(/\?{2,}/g, "?").trim();
    clean = clean.replace(/(\d+(?:[.,]\d+)?)\s*(lucas?|k)\b/gi, (_, n) => fmt(Math.round(parseFloat(n.replace(",", ".")) * 1000)));
    clean = clean.charAt(0).toUpperCase() + clean.slice(1);
    const t = strip(clean) + " " + strip(raw);

    const intents = [];
    for (const [name, re] of INTENTS) if (re.test(name === "SLOT_SELECTION" || name === "GREETING" ? strip(raw).trim() : t)) intents.push(name);
    if (budget && !intents.includes("BUDGET_STATEMENT")) intents.push("BUDGET_STATEMENT");
    if (intents.length === 0) intents.push("GENERAL_INFO");

    const ent = {};
    const svc = items.find((it) => it.keywords.some((k) => new RegExp(`\\b${strip(k).replace(/[-]/g, "[- ]?")}\\b`).test(t)));
    if (svc) { ent.service_keyword = svc.keywords.find((k) => new RegExp(`\\b${strip(k)}\\b`).test(t)) || svc.keywords[0]; ent.catalog_item_id = svc.id; }
    if (intents.includes("CASH_DISCOUNT")) ent.payment_type = "CASH";
    else if (intents.includes("FINANCING_CALCULATION")) ent.payment_type = "FINANCING";
    if (intents.includes("INSURANCE_INQUIRY")) ent.insurance = (t.match(/delta dental|cigna|metlife|ppo|hmo/) || [lang === "es" ? "seguro" : "insurance"])[0];
    if (budget) { ent.budget_amount = budget; ent.budget_currency = "LOCAL_OR_UNSPECIFIED"; }
    if (intents.includes("OBJECTION_EXPENSIVE")) ent.price_objection = true;
    const rel = relativeDate(t);
    if (rel) ent.proposed_date_relative = rel;
    if (time) ent.proposed_time = time;
    if (/saliendo de(l)? (la chamba|trabajo|trabajar)|after work|despues del trabajo|salgo del trabajo/.test(t)) {
      const [h, m] = (time || "18:00").split(":").map(Number);
      const end = h * 60 + m - 30;
      ent.work_end_constraint = `${String(Math.floor(end / 60)).padStart(2, "0")}:${String(end % 60).padStart(2, "0")}`;
    }
    const after = t.match(/\bafter (\d{1,2})\b|\bdespues de las (\d{1,2})\b/);
    if (after && !ent.work_end_constraint) { const h = parseInt(after[1] || after[2], 10); ent.work_end_constraint = `${(h < 8 ? h + 12 : h)}:00`; }
    const sel = strip(raw).trim().match(/^(?:opcion |option |la |the )?(1|2|3|primera|segunda|tercera|first|second|third)/);
    if (intents.includes("SLOT_SELECTION") && sel) ent.selected_slot_index = { "1": 1, "2": 2, "3": 3, primera: 1, segunda: 2, tercera: 3, first: 1, second: 2, third: 3 }[sel[1]];

    const order = ["SCHEDULE_REQUEST", "OBJECTION_EXPENSIVE", "FINANCING_CALCULATION", "PRICE_INQUIRY"];
    let primary = intents[0];
    if (intents.includes("SCHEDULE_REQUEST") && intents.includes("OBJECTION_EXPENSIVE")) primary = "SCHEDULE_AND_PRICE_OBJECTION";
    else if (intents.includes("FINANCING_CALCULATION") && intents.includes("SCHEDULE_REQUEST")) primary = "FINANCING_AND_SCHEDULE";
    else primary = order.find((o) => intents.includes(o)) || intents[0];

    return {
      detected_language: lang,
      regional_slang_detected: [...new Set(slang)],
      canonical_meaning: clean,
      primary_intent: primary,
      secondary_intents: intents.filter((i) => i !== primary),
      extracted_entities: ent,
      _ms: Math.max(1, Math.round(performance.now() - t0))
    };
  }

  return { normalize, detectLanguage, strip };
})();
