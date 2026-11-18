// ===== Live API Mode: same Hub, real backend (Flask /api/hub/*). Plain fetch(), no libraries. =====
// Turns on when (a) the Hub is served by the backend at /hub, or (b) a backend URL + key were saved in ⚙ API.
// Any failure → falls back to the built-in demo data without breaking the page.
const Live = (() => {
  const store = { get: (k) => { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } },
                  set: (k, v) => { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k); } catch (e) { /* storage blocked */ } } };
  const cfg = { base: store.get("ptd.hub.base"), key: store.get("ptd.hub.key"), tenant: store.get("ptd.hub.tenant"), cookie: false, on: false, estado: null, leads: [], sender: null, error: "" };
  const CRM_KEY = { peruptd_native: "native", salesforce: "salesforce", hubspot: "hubspot", pipedrive: "pipedrive", zoho: "zoho" };
  const COLS = { list_price: "list_price", cash_price: "cash_price", min_down_pct: "min_down_payment_pct", rec_down_pct: "recommended_down_payment_pct",
                 annual_rate_pct: "annual_rate_pct", max_term_years: "max_term_years" };
  const hue = (s) => [...String(s)].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7);

  async function api(path, opts = {}) {
    // same-origin with a CRM session (cookie + CSRF header) or machine access (X-Hub-Key + X-Tenant-Id)
    const auth = cfg.cookie ? { "X-PTD-CSRF": "1" } : { "X-Hub-Key": cfg.key, "X-Tenant-Id": cfg.tenant };
    const r = await fetch(cfg.base.replace(/\/$/, "") + path, { credentials: cfg.cookie ? "same-origin" : "omit", ...opts,
      headers: { "Content-Type": "application/json", ...auth, ...(opts.headers || {}) } });
    if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 160)}`);
    return r.status === 204 ? null : r.json();
  }

  const mapMedia = (m) => ({ id: m.id, type: m.media_type, trigger: m.trigger_moment, url: m.file_url, hue: hue(m.id || m.file_url),
                             caption: { es: m.caption_es || "", en: m.caption_en || m.caption_es || "" } });
  function mapItem(r, crmKey) {
    const sp = r.specs_json || {};
    return { id: r.id, live: true, external: { [crmKey]: r.external_crm_id || String(r.id).slice(0, 8) }, keywords: r.keywords || [],
      name: { es: r.name_es, en: r.name_en || r.name_es }, category: { es: r.category || "", en: r.category || "" }, status: r.status || "available",
      specs: { es: sp.es || sp.en || {}, en: sp.en || sp.es || {} }, list_price: +r.list_price, cash_price: +(r.cash_price ?? r.list_price), currency: r.currency,
      min_down_pct: +r.min_down_payment_pct, rec_down_pct: +r.recommended_down_payment_pct, annual_rate_pct: +r.annual_rate_pct, max_term_years: +r.max_term_years,
      promo: { es: r.promo_bonus_es || "", en: r.promo_bonus_en || r.promo_bonus_es || "" }, value: { es: r.value_comparison_es || "", en: r.value_comparison_en || r.value_comparison_es || "" },
      insurance: r.insurance_es ? { es: r.insurance_es, en: r.insurance_en || r.insurance_es } : undefined, media: (r.media || []).map(mapMedia) };
  }

  async function conectar(base, key, tenantId) {
    if (base !== undefined) { cfg.base = base.trim(); cfg.key = key.trim(); cfg.tenant = (tenantId || "").trim(); cfg.cookie = false; }
    cfg.error = "";
    try {
      const est = await api("/api/hub/estado");
      const crmKey = CRM_KEY[est.crm_type] || "native";
      const items = (await api("/api/hub/catalogo")).map((r) => mapItem(r, crmKey));
      const plantilla = INDUSTRIES[est.industry] || INDUSTRIES.realestate;
      INDUSTRIES.live = { ...plantilla, icon: "🔌", name: { en: est.name, es: est.name }, company: est.name, advisor: est.advisor_name || "",
        botName: { en: est.bot_name || "Ava", es: est.bot_name || "Ava" }, location: { en: est.address || "", es: est.address || "" }, mapsUrl: "",
        items: items.length ? items : plantilla.items, seed: [] };
      cfg.estado = est; cfg.on = true;
      cfg.sender = "hub:+1999" + String(Math.floor(1e6 + Math.random() * 9e6));
      if (!cfg.cookie) { store.set("ptd.hub.base", cfg.base); store.set("ptd.hub.key", cfg.key); store.set("ptd.hub.tenant", cfg.tenant); }
      S.ind = "live"; S.crm = crmKey; S.lang = est.default_language === "en" ? "en" : S.lang; S.logs = [];
      newLead(); await cargarLeads();
      return true;
    } catch (e) {
      cfg.on = false; cfg.error = String(e.message || e);
      if (S.ind === "live") { S.ind = "realestate"; newLead(); }
      return false;
    }
  }

  function desconectar() {
    cfg.on = false; cfg.estado = null; store.set("ptd.hub.base", ""); store.set("ptd.hub.key", ""); store.set("ptd.hub.tenant", ""); cfg.cookie = false;
    delete INDUSTRIES.live; S.ind = "realestate"; S.crm = "salesforce"; S.logs = []; newLead();
  }

  async function chat(texto) {
    const d = await api("/api/hub/chat", { method: "POST", body: JSON.stringify({ sender_id: cfg.sender, texto, canal_origen: S.channel === "wa" ? "WhatsApp" : "SMS (Twilio)" }) });
    const n = d.nlu || {};
    const nlu = { detected_language: n.detected_language || "es", regional_slang_detected: n.regional_slang_detected || [], canonical_meaning: n.clean_text || texto,
      primary_intent: n.primary_intent || "GENERAL_INFO", secondary_intents: (n.intents || []).filter((i) => i !== n.primary_intent),
      extracted_entities: Object.fromEntries(Object.entries(n.entities || {}).filter(([, v]) => v !== null && v !== false && !(Array.isArray(v) && !v.length))),
      _ms: n.ms || 0, source: n.source };
    const L0 = d.lead || {};
    Object.assign(lead, { stage: L0.stage || lead.stage, payment_method: L0.pay || lead.payment_method, stated_budget: L0.budget || lead.stated_budget,
      price_objection_count: L0.obj ?? lead.price_objection_count, preferred_language: L0.lang || nlu.detected_language,
      interested_catalog_item_id: nlu.extracted_entities.catalog_item_id || lead.interested_catalog_item_id || (IND().items[0] || {}).id });
    const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
    const toSlot = (iso) => { const t = new Date(iso); return { off: Math.round((new Date(t).setHours(0, 0, 0, 0) - hoy) / 864e5), time: `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}` }; };
    if (d.slots && d.slots.length) lead.offered_slots = d.slots.map(toSlot);
    if (L0.appointment) { lead.appointment = { ...toSlot(L0.appointment), label: new Date(L0.appointment).toLocaleString(S.lang === "es" ? "es-PE" : "en-US", { weekday: "short", hour: "numeric", minute: "2-digit" }) }; lead.offered_slots = null; }
    const media = (d.media || []).map((m) => ({ ...mapMedia(m), id: m.id || m.file_url }));
    media.forEach((m) => lead.sent_media_ids.includes(m.id) || lead.sent_media_ids.push(m.id));
    cargarLeads();
    return { nlu, result: { text: d.reply || "…", media, trace: (d.traza || []).map((t) => [t[0], String(t[1])]), alerts: d.alertas || [], crm: { stage: lead.stage, budget: 1, payment: 1, objections: 1 } } };
  }

  const pendientes = {};
  function guardarCampo(item, clave, valor, lang) {
    if (!cfg.on || !item.live) return;
    const col = COLS[clave] || (clave === "promo" ? `promo_bonus_${lang}` : clave === "value" ? `value_comparison_${lang}` : null);
    if (!col) return;
    clearTimeout(pendientes[item.id + col]);
    pendientes[item.id + col] = setTimeout(() => api(`/api/hub/catalogo/${item.id}`, { method: "PATCH", body: JSON.stringify({ [col]: valor }) })
      .then(() => toast(S.lang === "es" ? "Guardado en el CRM ✓" : "Saved to the CRM ✓")).catch((e) => toast("⚠ " + e.message, true)), 600);
  }

  async function sincronizar() {
    const r = await api("/api/hub/catalogo/sincronizar", { method: "POST" });
    await conectar();
    return r;
  }

  async function cargarLeads() {
    try { cfg.leads = await api("/api/hub/leads"); } catch (e) { cfg.leads = []; }
    return cfg.leads;
  }

  async function accion(senderId, nombre) {
    const r = await api(`/api/hub/leads/${encodeURIComponent(senderId)}/comando`, { method: "POST", body: JSON.stringify({ comando: nombre }) });
    await cargarLeads();
    return r;
  }

  async function arrancar() {
    if (new URLSearchParams(location.search).has("demo")) return false;      // /app?demo=1: pure recording demo
    if (cfg.base && cfg.key && cfg.tenant) return conectar();
    if (/^https?:/.test(location.protocol) && /\/hub\/?$/.test(location.pathname)) {
      cfg.base = location.origin;               // served by the backend: reuse the CRM session if there is one
      try { const r = await fetch("/api/hub/me", { credentials: "same-origin" }); if (r.ok) { cfg.cookie = true; return conectar(); } } catch (e) { /* no session */ }
    }
    return false;
  }

  return { cfg, conectar, desconectar, chat, guardarCampo, sincronizar, cargarLeads, accion, arrancar };
})();

function toast(texto, malo) {
  const t = el("div", { class: "toast" + (malo ? " bad" : ""), role: "status" }, texto);
  document.body.append(t);
  setTimeout(() => t.remove(), 2600);
}

function renderLivePanel() {
  const L = S.lang === "es";
  const base = el("input", { id: "live-base", type: "url", placeholder: "https://agent.example.run.app", value: Live.cfg.base, "aria-label": "Backend URL" });
  const key = el("input", { id: "live-key", type: "password", placeholder: "HUB_API_KEY", value: Live.cfg.key, "aria-label": "Hub API key" });
  const ten = el("input", { id: "live-tenant", type: "text", placeholder: "demo-realestate", value: Live.cfg.tenant, "aria-label": "Tenant id" });
  const estado = el("p", { class: "live-msg" }, Live.cfg.on ? `✅ ${L ? "Conectado a" : "Connected to"} ${Live.cfg.estado.name} · ${Live.cfg.estado.crm_type} · ${Live.cfg.estado.catalog_items} ${L ? "productos" : "products"}`
    : Live.cfg.error ? `⚠ ${Live.cfg.error}` : (L ? "Sin backend: el Hub usa los datos de demostración." : "No backend: the Hub is using built-in demo data."));
  const panel = el("div", { class: "live-panel", id: "live-panel", role: "dialog", "aria-label": "Live API" },
    el("h3", {}, L ? "Modo API en vivo" : "Live API Mode"),
    el("label", {}, L ? "URL del backend" : "Backend URL", base), el("label", {}, "HUB_API_KEY", key), el("label", {}, "Tenant ID", ten), estado,
    el("div", { class: "controls" },
      el("button", { class: "btn primary small", onclick: async () => { estado.textContent = "…"; const ok = await Live.conectar(base.value, key.value, ten.value); render(); if (!ok) { renderLivePanel(); } } }, L ? "Conectar" : "Connect"),
      Live.cfg.on ? el("button", { class: "btn small", onclick: () => { Live.desconectar(); render(); } }, L ? "Volver a la demo" : "Back to demo") : null,
      el("button", { class: "btn small", onclick: () => $("#live-panel").remove() }, L ? "Cerrar" : "Close")),
    el("p", { class: "live-note" }, L ? "Dentro de claude.ai la página no puede llamar a otros dominios: usa el Hub servido por tu backend en /hub (o entra a /app)."
      : "Inside claude.ai the page can't call other domains: use the Hub served by your backend at /hub (or log in at /app)."));
  const prev = $("#live-panel"); if (prev) prev.remove();
  document.body.append(panel);
}
