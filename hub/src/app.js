// ===== PeruPTD AI Sales Hub — UI =====
const T = {
  en: { tagline: "Autonomous AI Sales Agent · Multi-CRM", lang: "Language", industry: "Industry", crm: "CRM",
    tab1: "Live NLU & Chat Console", tab2: "Catalog, Pricing & Media", tab3: "Pipeline & 14-Day Follow-up",
    play: "Play", type: "Type like a real customer… (typos, slang, Spanglish)", send: "Send",
    debounce: (n, s) => `Debounce: ${n} fragment${n > 1 ? "s" : ""} — waiting ${s}s for more…`, debounceDone: (n) => `Batched ${n} message${n > 1 ? "s" : ""} into 1 reply`,
    active: "Bot active", paused: (t) => `Paused until ${t} — human handling`, xray: "AI Brain X-Ray", xrayTag: "live NLU translation",
    s1: "Batch & normalize", s2: "Layer 1 · Semantic NLU", s3: "Layer 2 · Deterministic engines", s4: "Layer 3 · Bilingual composer",
    idle: "Send a message or press Play to watch the agent think.", slang: "slang / typos", intents: "intents", entities: "entities",
    lang_detected: "language", media: "media", guard: ["no invented numbers", "forbidden phrases: clean", "anti-repetition < 80%", "max 2 files, no repeats"],
    rec: "record", calendar: "Live calendar", feed: "Rep alerts", ctrl: "Rep controls", repReply: "Rep replies from phone", resume: "Resume bot", rescue: "Left on read 24h → rescue", reset: "New conversation",
    synced: "Synced", catalogTitle: "Catalog lives in your CRM — the agent reads it live", list: "List price", cash: "Cash price", mindown: "Min down %", recdown: "Rec. down %", rate: "APR %", term: "Max term (yrs)",
    promo: "Promo / bonus", value: "\"Too expensive\" value argument", addMedia: "Add media", trigger: "Trigger", addBtn: "+ Add", editHint: "Edit any price — the agent uses it on the next message.",
    stages: { new: "New", qualified: "Qualified", booked: "Appointment booked", visited: "Attended", negotiation: "Negotiation (Day 10)", won: "Won", lost: "Lost" },
    you: "Live demo lead", day: "Day", attended: "Attended", noshow: "No-show", pause: "Pause 2h", sold: "Sold", followTitle: "14-day post-visit protocol", pick: "Pick a lead to see its follow-up", log: "Activity",
    status: { available: "Available", last_units: "Last units", sold_out: "Sold out" }, mediaTypes: { image: "Image", pdf: "PDF", video: "Video" } },
  es: { tagline: "Agente Comercial IA Autónomo · Multi-CRM", lang: "Idioma", industry: "Industria", crm: "CRM",
    tab1: "Consola en vivo NLU & Chat", tab2: "Catálogo, precios y multimedia", tab3: "Embudo y seguimiento 14 días",
    play: "Reproducir", type: "Escribe como un cliente real… (errores, jerga, Spanglish)", send: "Enviar",
    debounce: (n, s) => `Debounce: ${n} fragmento${n > 1 ? "s" : ""} — esperando ${s} s por si sigue escribiendo…`, debounceDone: (n) => `Agrupé ${n} mensaje${n > 1 ? "s" : ""} en 1 sola respuesta`,
    active: "Bot activo", paused: (t) => `En pausa hasta las ${t} — atiende el asesor`, xray: "Rayos X del cerebro IA", xrayTag: "traducción NLU en vivo",
    s1: "Agrupar y normalizar", s2: "Capa 1 · NLU semántico", s3: "Capa 2 · Motores determinísticos", s4: "Capa 3 · Redactor bilingüe",
    idle: "Envía un mensaje o pulsa Reproducir para ver cómo piensa el agente.", slang: "jerga / errores", intents: "intenciones", entities: "entidades",
    lang_detected: "idioma", media: "multimedia", guard: ["sin números inventados", "frases prohibidas: limpio", "anti-repetición < 80%", "máx. 2 archivos, sin repetir"],
    rec: "registro", calendar: "Agenda en vivo", feed: "Alertas al asesor", ctrl: "Controles del asesor", repReply: "El asesor responde desde su celular", resume: "Reactivar bot", rescue: "Lo dejó en visto 24 h → rescate", reset: "Nueva conversación",
    synced: "Sincronizado", catalogTitle: "El catálogo vive en tu CRM — el agente lo lee en vivo", list: "Precio lista", cash: "Precio contado", mindown: "Inicial mín. %", recdown: "Inicial recom. %", rate: "Tasa anual %", term: "Plazo máx. (años)",
    promo: "Promo / bono", value: "Argumento contra \"está caro\"", addMedia: "Agregar multimedia", trigger: "Momento", addBtn: "+ Agregar", editHint: "Edita cualquier precio: el agente lo usa en el siguiente mensaje.",
    stages: { new: "Nuevo", qualified: "Calificado", booked: "Cita agendada", visited: "Asistió", negotiation: "Negociación (Día 10)", won: "Vendido", lost: "Perdido" },
    you: "Lead de la demo en vivo", day: "Día", attended: "Vino", noshow: "No vino", pause: "Pausar 2 h", sold: "Vendido", followTitle: "Protocolo post-visita de 14 días", pick: "Elige un lead para ver su seguimiento", log: "Actividad",
    status: { available: "Disponible", last_units: "Últimas unidades", sold_out: "Agotado" }, mediaTypes: { image: "Imagen", pdf: "PDF", video: "Video" } }
};
const TRIGGERS = ["FIRST_INFO", "SPECS_PDF", "OPTION_RENDER", "PRICE_OBJECTION", "LOCATION_FACADE", "POST_VISIT_45M", "RESCUE_24H", "VIDEO_TOUR"];
const ICON = { image: "🖼️", pdf: "📄", video: "🎬" };
const FIELD_NAMES = {
  native: { stage: "stage", payment: "payment_method", budget: "stated_budget", objections: "price_objection_count", language: "preferred_language", item: "interested_catalog_item_id", media: "sent_media_ids", appointment: "appointment_datetime", channel: "channel_origin" },
  salesforce: { stage: "Status", payment: "Payment_Method__c", budget: "Initial_Budget__c", objections: "Price_Objection_Count__c", language: "Preferred_Language__c", item: "Interested_Product__c", media: "Media_Sent__c", appointment: "Event.StartDateTime", channel: "LeadSource" },
  hubspot: { stage: "dealstage", payment: "payment_method", budget: "amount", objections: "price_objection_count", language: "hs_language", item: "line_item", media: "media_sent", appointment: "meeting.hs_meeting_start_time", channel: "hs_analytics_source" },
  pipedrive: { stage: "deal.stage_id", payment: "Payment method", budget: "deal.value", objections: "Price objections", language: "Language", item: "deal.product", media: "Media sent", appointment: "activity.due_date", channel: "deal.origin" },
  zoho: { stage: "Lead_Status", payment: "Payment_Method", budget: "Budget", objections: "Price_Objections", language: "Language", item: "Product_Interest", media: "Media_Sent", appointment: "Events.Start_DateTime", channel: "Lead_Source" }
};

const S = { lang: "en", ind: "realestate", crm: "salesforce", tab: "tab1", channel: "wa", busy: false, pending: [], timer: null, selected: "live", lastNLU: null, pausedUntil: null, alerts: [], logs: [] };
let lead;
const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
};
const t = (k) => T[S.lang][k];
const IND = () => INDUSTRIES[S.ind];
const now = () => new Date().toLocaleTimeString(S.lang === "es" ? "es-PE" : "en-US", { hour: "numeric", minute: "2-digit" });

function newLead() {
  lead = { stage: "new", sent_media_ids: [], price_objection_count: 0, preferred_language: S.lang, channel_origin: S.channel === "wa" ? "WhatsApp" : "SMS (Twilio)", greeted: false, offered_slots: null, appointment: null, follow: {} };
  S.lastNLU = null; S.alerts = []; S.pausedUntil = null; S.pending = [];
}

// ---------------- top bar ----------------
function renderTop() {
  const seg = (key, opts) => el("div", { class: "seg", role: "group" }, opts.map(([v, label]) => el("button", { "aria-pressed": S[key] === v ? "true" : "false", onclick: () => { if (S[key] === v) return; S[key] = v; if (key === "ind") newLead(); if (key === "lang" && lead.stage === "new" && !lead.greeted) lead.preferred_language = v; render(); } }, label)));
  $("#top").replaceChildren(
    el("div", { class: "brand" }, el("div", { class: "mark" }, "PTD"), el("div", {}, el("h1", {}, "PeruPTD AI Sales Hub"), el("small", {}, t("tagline")))),
    el("div", { class: "switch" }, el("span", {}, t("lang")), seg("lang", [["en", "🇺🇸 English"], ["es", "🇪🇸 Español"]])),
    el("div", { class: "switch" }, el("span", {}, t("industry")), seg("ind", Object.entries(INDUSTRIES).map(([k, v]) => [k, `${v.icon} ${v.name[S.lang]}`]))),
    el("div", { class: "switch" }, el("span", {}, t("crm")), seg("crm", Object.entries(CRMS).map(([k, v]) => [k, v.short])))
  );
  const n = lead.stage !== "new" ? 1 : 0;
  $("#tabs").replaceChildren(...["tab1", "tab2", "tab3"].map((k) => el("button", { role: "tab", "aria-selected": S.tab === k ? "true" : "false", onclick: () => { S.tab = k; render(); } }, t(k), k === "tab3" && n ? el("span", { class: "count" }, "LIVE") : null)));
}

// ---------------- tab 1 ----------------
function thumb(m, lang) {
  return el("div", { class: "thumb" }, el("div", { class: "art", style: `background: linear-gradient(135deg, hsl(${m.hue} 55% 46%), hsl(${(m.hue + 40) % 360} 60% 32%))` }, ICON[m.type]),
    el("div", { class: "cap" }, m.caption[lang], el("span", { class: "trg" }, m.trigger)));
}

function addMsg(kind, text, extra = {}) {
  const box = $("#msgs"); if (!box) return;
  const ind = IND();
  const who = kind === "bot" ? `${ind.botName[S.lang]} · AI` : kind === "rep" ? `${ind.advisor} · 📱` : null;
  const rich = String(text).split(/(\*[^*\n]+\*)/).map((p) => /^\*[^*]+\*$/.test(p) ? el("b", {}, p.slice(1, -1)) : p);
  const bubble = el("div", { class: "bubble" }, who ? el("div", { class: "who" }, who) : null, rich,
    extra.media && extra.media.length ? el("div", { class: "media-row" }, extra.media.map((m) => thumb(m, extra.lang || S.lang))) : null,
    el("div", { class: "time" }, now() + (kind !== "me" ? " ✓✓" : "")));
  const row = el("div", { class: `row ${kind}` }, kind === "sys" ? el("div", { class: "sysnote" }, text) : bubble);
  box.append(row); box.scrollTop = box.scrollHeight;
  if (!extra.noStore) S.logs.push({ kind, text, media: extra.media, lang: extra.lang });
  return row;
}

function setStage(n, cls) { const st = $(`#st${n}`); if (st) st.className = `stage ${cls || ""}`; }

function receive(text) {
  if (!text.trim()) return;
  addMsg("me", text);
  if (S.pausedUntil) { addMsg("sys", S.lang === "es" ? "Mensaje guardado en el CRM. El bot no responde: el asesor está atendiendo." : "Message logged to the CRM. Bot stays quiet: a human is handling this chat."); return; }
  S.pending.push(text);
  clearInterval(S.timer);
  let left = 15;
  const strip = $("#strip-text");
  const tick = () => { if (strip) strip.textContent = t("debounce")(S.pending.length, left); };
  tick(); setStage(1, "on");
  S.timer = setInterval(() => { left -= 3; if (left <= 0) { clearInterval(S.timer); flush(); } else tick(); }, 600);
}

async function flush() {
  const batch = S.pending.splice(0);
  if (!batch.length) return;
  const strip = $("#strip-text"); if (strip) strip.textContent = t("debounceDone")(batch.length);
  const ind = IND();
  const nlu = NLU.normalize(batch.join("\n"), { items: ind.items, previousLanguage: lead.preferred_language });
  S.lastNLU = { batch, nlu, result: null };
  lead.preferred_language = nlu.detected_language;
  renderXray(1);
  const typing = $("#msgs").appendChild(el("div", { class: "row bot" }, el("div", { class: "bubble typing" }, el("i"), el("i"), el("i"))));
  $("#msgs").scrollTop = $("#msgs").scrollHeight;
  await wait(650); renderXray(2);
  const result = Engines.run(nlu, { lead, industry: ind, lang: nlu.detected_language, crmKey: S.crm });
  S.lastNLU.result = result;
  await wait(650); renderXray(3);
  await wait(500);
  typing.remove();
  addMsg("bot", result.text, { media: result.media, lang: nlu.detected_language });
  renderXray(4);
  result.alerts.forEach((a) => S.alerts.unshift({ text: a, hot: /URGENT|URGENTE|call|llamar|New|Nueva/.test(a), time: now() }));
  renderSide(result.crm);
  renderComposer();
}

function renderXray(step) {
  const x = S.lastNLU; const box = $("#xbody"); if (!box) return;
  if (!x) { box.replaceChildren(el("p", { class: "muted-x" }, t("idle")), ...[1, 2, 3, 4].map((n) => el("div", { class: "stage", id: `st${n}` }, el("h3", {}, el("span", { class: "n" }, `0${n}`), t(`s${n}`))))); return; }
  const { batch, nlu, result } = x;
  const ent = nlu.extracted_entities;
  const s1 = el("div", { class: `stage ${step === 1 ? "on" : "done"}`, id: "st1" }, el("h3", {}, el("span", { class: "n" }, "01"), t("s1"), el("span", { class: "ms" }, `${batch.length} msg · 15 s`)),
    el("div", { class: "raw" }, batch.map((b) => `› ${b}`).join("\n")));
  const s2 = el("div", { class: `stage ${step === 2 ? "on" : step > 2 ? "done" : ""}`, id: "st2" }, el("h3", {}, el("span", { class: "n" }, "02"), t("s2"), el("span", { class: "ms" }, `${nlu._ms} ms · ${t("lang_detected")}: ${nlu.detected_language.toUpperCase()}`)),
    el("div", { class: "canon" }, "“" + nlu.canonical_meaning + "”"),
    nlu.regional_slang_detected.length ? el("div", { class: "slangs" }, nlu.regional_slang_detected.map((s) => { const m = s.match(/^(.*?) \((.*)\)$/); return el("span", { class: "slang" }, el("b", {}, m ? m[1] : s), " → ", el("em", {}, m ? m[2] : "")); })) : null,
    el("div", { class: "intents" }, el("span", { class: "intent primary" }, nlu.primary_intent), nlu.secondary_intents.map((i) => el("span", { class: "intent" }, i))),
    el("dl", { class: "ents" }, Object.entries(ent).flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, typeof v === "number" ? v.toLocaleString("en-US") : String(v))])),
    el("details", { class: "json" }, el("summary", {}, "NormalizedTurn JSON"), el("pre", {}, JSON.stringify((({ _ms, ...r }) => r)(nlu), null, 2))));
  const s3 = el("div", { class: `stage ${step === 3 ? "on" : step > 3 ? "done" : ""}`, id: "st3" }, el("h3", {}, el("span", { class: "n" }, "03"), t("s3"), el("span", { class: "ms" }, CRMS[S.crm].short + " catalog")),
    step >= 3 && result ? el("ul", { class: "trace" }, result.trace.map(([a, b]) => el("li", {}, el("b", {}, a), el("span", {}, b)))) : el("p", { class: "muted-x" }, "…"));
  const s4 = el("div", { class: `stage ${step === 4 ? "on" : ""}`, id: "st4" }, el("h3", {}, el("span", { class: "n" }, "04"), t("s4"), el("span", { class: "ms" }, `${t("lang_detected")}: ${nlu.detected_language.toUpperCase()}`)),
    step >= 4 && result ? [el("div", { class: "muted-x" }, `${t("media")}: ${result.media.length ? result.media.map((m) => m.caption[nlu.detected_language]).join(" + ") : "—"}`), el("div", { class: "guard" }, t("guard").map((g) => el("span", {}, "✓ " + g)))] : el("p", { class: "muted-x" }, "…"));
  box.replaceChildren(s1, s2, s3, s4);
}

function fieldRows(crmDelta) {
  const F = FIELD_NAMES[S.crm], ind = IND(), L = S.lang;
  const item = ind.items.find((i) => i.id === lead.interested_catalog_item_id);
  const rows = [
    ["stage", t("stages")[lead.stage] || lead.stage], ["channel", lead.channel_origin], ["language", (lead.preferred_language || "").toUpperCase()],
    ["item", item ? item.name[L] : "—"], ["payment", lead.payment_method ? (lead.payment_method === "CASH" ? (L === "es" ? "Contado" : "Cash") : (L === "es" ? "Financiamiento" : "Financing")) : "—"],
    ["budget", lead.stated_budget ? Engines.money(lead.stated_budget, L) : "—"], ["objections", `${lead.price_objection_count || 0} / 3`],
    ["media", lead.sent_media_ids.length ? lead.sent_media_ids.join(", ") : "—"], ["appointment", lead.appointment ? lead.appointment.label : "—"]
  ];
  const changed = new Set(Object.keys(crmDelta || {}));
  if (crmDelta && crmDelta.item) changed.add("item");
  return rows.map(([k, v]) => el("div", { class: "field" + (changed.has(k) || (k === "stage" && crmDelta && crmDelta.stage) ? " flash" : "") }, el("code", {}, F[k]), el("span", {}, v)));
}

function renderCalendar() {
  const box = el("div", { class: "cal" });
  const days = [0, 1, 2].map((o) => { const d = new Date(); d.setDate(d.getDate() + (lead.offered_slots ? lead.offered_slots[0].off + o : 1 + o)); return d; });
  box.append(el("div"), ...days.map((d) => el("div", { class: "hd" }, d.toLocaleDateString(S.lang === "es" ? "es-PE" : "en-US", { weekday: "short", day: "numeric" }))));
  const base = lead.offered_slots ? lead.offered_slots[0].off : 1;
  for (let h = 9; h <= 20; h++) {
    box.append(el("div", { class: "hr" }, `${h}:00`));
    [0, 1, 2].forEach((o) => {
      const off = base + o;
      const hit = (s) => s && s.off === off && parseInt(s.time, 10) === h;
      let cls = "c";
      if ((off === 1 && h === 19) || (off === 2 && h === 10) || (h === 13)) cls += " busy";
      if (lead.offered_slots && lead.offered_slots.some(hit)) cls += " offer";
      if (lead.appointment && hit(lead.appointment)) cls = "c booked";
      box.append(el("div", { class: cls, title: `${h}:00` }));
    });
  }
  return box;
}

function renderSide(crmDelta) {
  const c = CRMS[S.crm], col = $("#crmcol"); if (!col) return;
  const statusPill = S.pausedUntil ? el("span", { class: "pill warn" }, t("paused")(S.pausedUntil)) : el("span", { class: "pill" }, t("active"));
  col.replaceChildren(
    el("section", { class: "panel" }, el("div", { class: "crmhead", style: `background:${c.color}` }, el("b", {}, `${c.name} · ${c.leadObj}`), el("small", {}, `${t("synced")} ${now()}`)), el("div", { class: "fields" }, fieldRows(crmDelta))),
    el("section", { class: "panel" }, el("h2", {}, "📅 ", t("calendar"), el("span", { class: "tag" }, `${c.eventObj} · Google/Outlook`)), renderCalendar()),
    el("section", { class: "panel" }, el("h2", {}, t("ctrl"), el("span", { class: "tag" }, statusPill)),
      el("div", { class: "controls" },
        S.pausedUntil ? el("button", { class: "btn small", onclick: () => { S.pausedUntil = null; renderSide(); renderStrip(); } }, "▶ " + t("resume"))
          : el("button", { class: "btn small", onclick: repReply }, "📱 " + t("repReply")),
        el("button", { class: "btn small", onclick: rescue }, "🛟 " + t("rescue")),
        el("button", { class: "btn small", onclick: () => { newLead(); render(); } }, "↺ " + t("reset")))),
    el("section", { class: "panel" }, el("h2", {}, "🔔 ", t("feed")), el("div", { class: "feed" }, S.alerts.length ? S.alerts.map((a) => el("div", { class: a.hot ? "hot" : "" }, `${a.time} · ${a.text}`)) : el("div", {}, "—")))
  );
  renderStrip();
}

function renderStrip() {
  const s = $("#strip-pill"); if (!s) return;
  s.replaceChildren(S.pausedUntil ? el("span", { class: "pill warn" }, t("paused")(S.pausedUntil)) : el("span", { class: "pill" }, t("active")));
}

function repReply() {
  const until = new Date(Date.now() + 2 * 3600e3).toLocaleTimeString(S.lang === "es" ? "es-PE" : "en-US", { hour: "numeric", minute: "2-digit" });
  addMsg("rep", S.lang === "es" ? "Hola, soy el asesor 👋 yo te ayudo personalmente con la visita." : "Hi, it's your rep 👋 I'll personally help you with the visit.");
  S.pausedUntil = until;
  S.alerts.unshift({ text: S.lang === "es" ? "Eco detectado: el asesor respondió a mano → bot en pausa 2 h" : "Echo detected: rep replied by hand → bot paused 2h", hot: true, time: now() });
  renderSide();
}

function rescue() {
  if (S.pausedUntil) return;
  const ind = IND(), item = ind.items.find((i) => i.id === lead.interested_catalog_item_id) || ind.items[0];
  const pick = item.media.find((m) => !lead.sent_media_ids.includes(m.id) && ["RESCUE_24H", "OPTION_RENDER", "POST_VISIT_45M", "VIDEO_TOUR", "SPECS_PDF"].includes(m.trigger));
  if (pick) lead.sent_media_ids.push(pick.id);
  const L = lead.preferred_language || S.lang;
  addMsg("bot", L === "es" ? `¡Hola! Te dejo algo más para que lo veas con calma 😊 ¿Te guardo un horario para conocer *${item.name.es}*?` : `Hey! Here's one more thing to look at when you have a minute 😊 Want me to hold a time for you to see the *${item.name.en}*?`, { media: pick ? [pick] : [], lang: L });
  S.alerts.unshift({ text: L === "es" ? "Rescate 24 h enviado dentro de la ventana gratuita de Meta" : "24h rescue sent inside Meta's free window", hot: false, time: now() });
  renderSide({ media: 1 });
}

function renderComposer() {
  const box = $("#composer"); if (!box) return;
  const ind = IND(), sc = ind.scenarios[S.lang];
  const playScenario = async () => { if (S.busy) return; S.busy = true; for (const p of sc.parts) { receive(p); await wait(900); } S.busy = false; };
  const chips = [el("button", { class: "chip play", onclick: playScenario }, `▶ ${t("play")}: ${sc.label}`)];
  if (lead.offered_slots) chips.push(...[1, 2, 3].map((n) => el("button", { class: "chip slot", onclick: () => receive(String(n)) }, `${n}️⃣`)));
  chips.push(...ind.quick[S.lang].map((q) => el("button", { class: "chip", onclick: () => receive(q) }, q)));
  const input = el("input", { id: "msg-input", type: "text", placeholder: t("type"), "aria-label": t("type"), onkeydown: (e) => { if (e.key === "Enter") { receive(e.target.value); e.target.value = ""; } } });
  box.replaceChildren(el("div", { class: "chips" }, chips), el("div", { class: "sendrow" }, input, el("button", { class: "btn primary", onclick: () => { receive(input.value); input.value = ""; } }, t("send"))));
}

function renderTab1() {
  const ind = IND();
  const chan = el("div", { class: "chan" }, [["wa", "WhatsApp"], ["sms", "SMS"]].map(([v, l]) => el("button", { "aria-pressed": S.channel === v ? "true" : "false", onclick: () => { S.channel = v; lead.channel_origin = v === "wa" ? "WhatsApp" : "SMS (Twilio)"; render(); } }, l)));
  const phone = el("section", { class: `panel phone ${S.channel === "sms" ? "sms" : ""}` },
    el("div", { class: "phone-head" }, el("div", { class: "avatar" }, "C"), el("div", {}, el("b", {}, ind.company), el("small", {}, S.channel === "wa" ? "WhatsApp Business · Meta Cloud API" : "SMS · Twilio +1 (512) 555-0100")), chan),
    el("div", { class: "status-strip" }, el("span", { id: "strip-text" }, "Debounce 15 s · Lead Ads 90 s"), el("span", { id: "strip-pill", class: "pill-wrap", style: "margin-left:auto" })),
    el("div", { class: "msgs", id: "msgs" }), el("div", { class: "composer", id: "composer" }));
  const xray = el("section", { class: "panel xray" }, el("h2", {}, "🧠 ", t("xray"), el("span", { class: "tag" }, t("xrayTag"))), el("div", { class: "xbody", id: "xbody" }));
  $("#tab1").replaceChildren(el("div", { class: "console" }, phone, xray, el("div", { class: "crmcol", id: "crmcol" })));
  for (const m of S.logs) addMsg(m.kind, m.text, { media: m.media, lang: m.lang, noStore: true });
  renderComposer(); renderXray(S.lastNLU ? 4 : 0); renderSide();
}

// ---------------- tab 2 ----------------
function renderTab2() {
  const ind = IND(), c = CRMS[S.crm], L = S.lang;
  const num = (item, key, label, step = "1") => el("label", {}, label, el("input", { type: "number", step, value: item[key], id: `${item.id}-${key}`, oninput: (e) => { item[key] = parseFloat(e.target.value) || 0; } }));
  const cards = ind.items.map((item) => {
    const trig = el("select", { id: `${item.id}-trig`, "aria-label": t("trigger") }, TRIGGERS.map((x) => el("option", { value: x }, x)));
    const typ = el("select", { id: `${item.id}-typ`, "aria-label": "type" }, Object.keys(ICON).map((x) => el("option", { value: x }, t("mediaTypes")[x])));
    return el("article", { class: "card" },
      el("header", {}, el("div", {}, el("h3", {}, item.name[L]), el("small", {}, `${c.short} ID ${item.external[S.crm]} · ${item.category[L]}`)),
        el("span", { class: "pill" + (item.status === "last_units" ? " warn" : "") }, t("status")[item.status])),
      el("div", { class: "specs" }, Object.entries(item.specs[L]).map(([k, v]) => el("span", {}, `${k}: ${v}`))),
      el("div", { class: "grid6" }, num(item, "list_price", t("list")), num(item, "cash_price", t("cash")), num(item, "min_down_pct", t("mindown")),
        num(item, "rec_down_pct", t("recdown")), num(item, "annual_rate_pct", t("rate"), "0.1"), num(item, "max_term_years", t("term"))),
      el("label", { class: "wide" }, t("promo"), el("textarea", { id: `${item.id}-promo`, oninput: (e) => { item.promo[L] = e.target.value; } }, item.promo[L])),
      el("label", { class: "wide" }, t("value"), el("textarea", { id: `${item.id}-value`, oninput: (e) => { item.value[L] = e.target.value; } }, item.value[L])),
      el("div", { class: "mediagrid" }, item.media.map((m) => thumb(m, L))),
      el("div", { class: "addmedia" }, t("addMedia") + ":", typ, trig, el("button", { class: "btn small", onclick: () => {
        const n = item.media.length + 1;
        item.media.push({ id: `${item.id}-u${n}`, type: typ.value, trigger: trig.value, caption: { en: `New ${typ.value} #${n}`, es: `Nuevo ${t("mediaTypes")[typ.value].toLowerCase()} #${n}` }, hue: (n * 47) % 360 });
        renderTab2();
      } }, t("addBtn"))));
  });
  $("#tab2").replaceChildren(
    el("div", { class: "syncbar" }, el("span", { class: "dot" }), el("b", {}, t("catalogTitle")), el("code", {}, c.catalogSrc), el("span", { style: "color:var(--muted)" }, `${t("synced")} ${now()} · ${t("editHint")}`)),
    el("div", { class: "cards" }, cards));
}

// ---------------- tab 3 ----------------
function boardLeads() {
  const ind = IND();
  const seeded = ind.seed.map((s, i) => ({ id: `s${i}`, ...s }));
  const live = { id: "live", name: t("you"), stage: lead.stage === "lost" ? "new" : lead.stage, lang: lead.preferred_language, channel: lead.channel_origin, pay: lead.payment_method, budget: lead.stated_budget, obj: lead.price_objection_count, day: lead.day || 0, live: true };
  return [live, ...seeded];
}

function protocolState(l, key) {
  const order = ["t24", "t75", "t45", "d2", "d5", "d10", "d14"];
  const done = { new: 0, qualified: 0, booked: 0, visited: 3, negotiation: 6, won: 7 }[l.stage] || 0;
  const dayDone = l.stage === "visited" ? Math.min(7, 3 + ((l.day >= 2) + (l.day >= 5))) : done;
  const i = order.indexOf(key);
  if (l.noshow && i >= 2) return "skip";
  if (l.stage === "won" && i >= dayDone) return "skip";
  if (i < dayDone) return "done";
  if (i === dayDone && ["booked", "visited", "negotiation"].includes(l.stage)) return "next";
  return "";
}

function renderTab3() {
  const leads = boardLeads(), ind = IND();
  const cols = ind.stages.map((st) => {
    const inCol = leads.filter((l) => l.stage === st);
    return el("div", { class: "col" }, el("h3", {}, t("stages")[st], el("span", {}, inCol.length)),
      inCol.map((l) => el("button", { class: "lead" + (l.live ? " live" : ""), onclick: () => { S.selected = l.id; renderTab3(); } },
        el("b", {}, l.name), el("div", { class: "meta" }, el("span", {}, l.lang === "es" ? "🇪🇸" : "🇺🇸"), el("span", {}, l.channel), l.budget ? el("span", {}, Engines.money(l.budget, S.lang)) : null),
        el("div", { class: "meta" }, el("span", { class: "strikes", title: "price objections" }, [1, 2, 3].map((n) => el("i", { class: n <= (l.obj || 0) ? "on" : "" }))), l.day ? el("span", {}, `${t("day")} ${l.day}`) : null))));
  });
  const sel = leads.find((l) => l.id === S.selected) || leads[0];
  const act = (fn) => () => { fn(sel); renderTab3(); };
  const setStage = (l, st) => { if (l.live) lead.stage = st; else ind.seed[parseInt(l.id.slice(1), 10)].stage = st; };
  const timeline = el("ol", { class: "timeline" }, PROTOCOL.map((p) => { const s = protocolState(sel, p.key); return el("li", { class: s }, el("span", { class: "ic" }, s === "done" ? "✓" : s === "next" ? "•" : ""), el("span", { class: "when" }, p.when[S.lang]), el("span", {}, p.what[S.lang]), s === "next" ? el("span", { class: "pill warn" }, S.lang === "es" ? "siguiente" : "next") : el("span")); }));
  const controls = el("div", { class: "controls" },
    el("button", { class: "btn small", onclick: act((l) => { setStage(l, "visited"); if (l.live) lead.day = 0; }) }, "✅ " + t("attended")),
    el("button", { class: "btn small", onclick: act((l) => { if (l.live) { lead.noshow = true; } else ind.seed[parseInt(l.id.slice(1), 10)].noshow = true; S.alerts.unshift({ text: S.lang === "es" ? "No vino → mensaje de reprogramación enviado" : "No-show → reschedule message sent", hot: true, time: now() }); }) }, "❌ " + t("noshow")),
    el("button", { class: "btn small", onclick: act(() => { repReply(); }) }, "⏸ " + t("pause")),
    el("button", { class: "btn small", onclick: act((l) => setStage(l, "won")) }, "🏆 " + t("sold")));
  $("#tab3").replaceChildren(el("div", { class: "board" }, cols),
    el("div", { class: "detail" },
      el("section", { class: "panel" }, el("h2", {}, t("followTitle"), el("span", { class: "tag" }, sel.name)), timeline, controls),
      el("section", { class: "panel" }, el("h2", {}, t("log"), el("span", { class: "tag" }, `${CRMS[S.crm].name} · ${CRMS[S.crm].leadObj}`)),
        el("div", { class: "feed", style: "max-height:330px" }, S.alerts.length ? S.alerts.map((a) => el("div", { class: a.hot ? "hot" : "" }, `${a.time} · ${a.text}`)) : el("div", {}, t("pick"))))));
}

// ---------------- boot ----------------
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
function render() {
  renderTop();
  for (const k of ["tab1", "tab2", "tab3"]) $("#" + k).hidden = S.tab !== k;
  if (S.tab === "tab1") renderTab1(); else if (S.tab === "tab2") renderTab2(); else renderTab3();
}
newLead();
document.addEventListener("DOMContentLoaded", () => {
  const prev = S.logs; render();
  // Leave the console in a realistic working state: play the scenario once on load.
  setTimeout(() => { if (!prev.length && !S.logs.length) $(".chip.play") && $(".chip.play").click(); }, 600);
});
