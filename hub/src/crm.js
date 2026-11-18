// ===== PeruPTD Native CRM (production) =====
// Served by Flask at /app: login against hub_users, then Pipeline (5-column Kanban + live conversation + commands),
// Catalog (CRUD + media uploads by role) and Settings (owner WhatsApp, hours, quiet window, forbidden phrases, follow-up
// texts, CRM field mapping). Every call carries the HttpOnly session cookie + X-PTD-CSRF; the server filters by tenant.
// /app?demo=1, file:// and the claude.ai artifact keep the recording demo untouched.
const CRM = (() => {
  const C = { me: null, estado: null, lang: "es", vista: "pipeline", leads: [], sel: null, msgs: [], items: [], editando: null, ajustes: null, timer: null };
  const TX = {
    es: { login: "Ingresar", email: "Correo", pass: "Contraseña", enter: "Entrar", out: "Salir", pipeline: "Pipeline", catalog: "Catálogo", settings: "Ajustes",
      cols: { capturado: "Capturado", calificado: "Calificado", visita_agendada: "Visita agendada", seguimiento_14d: "Seguimiento 14 días", cierre_alerta: "Cierre / Alerta" },
      alert: { objecion_3: "3ª objeción de precio", dia_10_llamar: "Día 10: llamar", confirmar_asistencia: "¿Vino a la visita?" },
      origin: { cliente: "Cliente", bot: "Agente IA", asesor: "Asesor", seguimiento: "Seguimiento" }, pick: "Elige un lead para ver la conversación.",
      send: "Enviar y pausar bot 2 h", write: "Escribe como asesor…", cmds: { vino: "✅ Vino", "no vino": "❌ No vino", pausa: "⏸ Pausar", activar: "▶ Activar", vendido: "🏁 Vendido" },
      newItem: "+ Nuevo producto", save: "Guardar", del: "Borrar", cancel: "Cancelar", upload: "Subir archivo", role: "Rol del archivo", caption: "Leyenda",
      sync: "⟳ Sincronizar desde tu CRM", empty: "Sin leads todavía.", saved: "Guardado ✓", readonly: "Solo un administrador puede cambiar esto.",
      confirmDel: "¿Borrar este producto y sus archivos?", files: "Archivos", noFiles: "Sin archivos aún." },
    en: { login: "Sign in", email: "Email", pass: "Password", enter: "Sign in", out: "Sign out", pipeline: "Pipeline", catalog: "Catalog", settings: "Settings",
      cols: { capturado: "Captured", calificado: "Qualified", visita_agendada: "Visit booked", seguimiento_14d: "14-day follow-up", cierre_alerta: "Close / Alert" },
      alert: { objecion_3: "3rd price objection", dia_10_llamar: "Day 10: call", confirmar_asistencia: "Did they show up?" },
      origin: { cliente: "Customer", bot: "AI agent", asesor: "Advisor", seguimiento: "Follow-up" }, pick: "Pick a lead to see the conversation.",
      send: "Send & pause bot 2 h", write: "Type as the advisor…", cmds: { vino: "✅ Attended", "no vino": "❌ No-show", pausa: "⏸ Pause", activar: "▶ Resume", vendido: "🏁 Won" },
      newItem: "+ New product", save: "Save", del: "Delete", cancel: "Cancel", upload: "Upload file", role: "File role", caption: "Caption",
      sync: "⟳ Sync from your CRM", empty: "No leads yet.", saved: "Saved ✓", readonly: "Only an admin can change this.",
      confirmDel: "Delete this product and its files?", files: "Files", noFiles: "No files yet." },
  };
  const x = (k) => TX[C.lang][k];
  const ROLES = ["FIRST_INFO", "SPECS_PDF", "PRICE_OBJECTION", "PROOF_RESULTS", "VIDEO_TOUR", "LOCATION_MAP"];
  const MODOS = { credito_inicial: { es: "Crédito / Inicial", en: "Financing / Down payment" }, seguro_medico: { es: "Seguro médico", en: "Medical insurance" },
                  elegibilidad: { es: "Elegibilidad", en: "Eligibility" }, b2b: { es: "B2B", en: "B2B" } };
  const DIAS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"];
  const esAdmin = () => C.me && C.me.rol === "admin";

  async function api(path, opts = {}) {
    const form = opts.body instanceof FormData;
    const r = await fetch(path, { credentials: "same-origin", ...opts,
      headers: { "X-PTD-CSRF": "1", ...(form || !opts.body ? {} : { "Content-Type": "application/json" }), ...(opts.headers || {}) } });
    const d = await r.json().catch(() => ({}));
    if (r.status === 401 && path !== "/api/hub/login") { pantallaLogin(); throw new Error(d.error || "401"); }
    if (!r.ok) throw new Error(d.error || `${r.status}`);
    return d;
  }
  const aviso = (txt, malo) => toast(txt, malo);
  const fecha = (iso) => iso ? new Date(iso).toLocaleString(C.lang === "es" ? "es-PE" : "en-US", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "";
  const dinero = (n) => n == null || n === "" ? "—" : "US$" + Number(n).toLocaleString("en-US");

  function marco() {
    document.body.classList.add("crm-mode");
    $("#top").replaceChildren(
      el("div", { class: "brand" }, el("div", { class: "mark" }, "PTD"), el("div", {}, el("h1", {}, C.estado ? C.estado.name : "PeruPTD Native CRM"),
        el("small", {}, C.me ? `${C.me.nombre} · ${C.me.rol}` : "PeruPTD Native CRM"))),
      el("div", { class: "seg" }, ...["es", "en"].map((l) => el("button", { "aria-pressed": C.lang === l ? "true" : "false", onclick: () => { C.lang = l; C.langFijo = true; pintar(); } }, l.toUpperCase()))),
      C.me ? el("button", { class: "btn small", onclick: salir }, x("out")) : null);
    $("#tabs").replaceChildren(...(C.me ? ["pipeline", "catalog", "settings"] : []).map((v) =>
      el("button", { role: "tab", "aria-selected": C.vista === v ? "true" : "false", onclick: () => { C.vista = v; pintar(); } }, x(v))));
    const main = $("main");
    main.replaceChildren(el("section", { class: "view", id: "crm" }));
    return $("#crm");
  }

  // ---------------- login ----------------
  function pantallaLogin(error) {
    clearInterval(C.timer); C.me = null;
    const caja = marco();
    const email = el("input", { type: "email", id: "crm-email", autocomplete: "username", required: true });
    const pass = el("input", { type: "password", id: "crm-pass", autocomplete: "current-password", required: true });
    const msg = el("p", { class: "crm-error", role: "alert" }, error || "");
    const form = el("form", { class: "crm-login panel", onsubmit: async (e) => {
      e.preventDefault(); msg.textContent = "…";
      try { await api("/api/hub/login", { method: "POST", body: JSON.stringify({ email: email.value, password: pass.value }) }); pass.value = ""; await cargar(); }
      catch (err) { msg.textContent = err.message; pass.value = ""; }
    } }, el("h2", {}, x("login")), el("label", {}, x("email"), email), el("label", {}, x("pass"), pass), msg,
      el("button", { class: "btn primary", type: "submit" }, x("enter")));
    caja.replaceChildren(form);
    email.focus();
  }

  async function salir() { await api("/api/hub/logout", { method: "POST" }).catch(() => {}); pantallaLogin(); }

  async function cargar() {
    C.me = (await api("/api/hub/me")).usuario;
    C.estado = await api("/api/hub/estado");
    if (!C.langFijo) C.lang = C.estado.default_language === "en" ? "en" : "es";
    await Promise.all([cargarLeads(), cargarCatalogo()]);
    clearInterval(C.timer);
    C.timer = setInterval(async () => { if (C.vista !== "pipeline" || document.hidden) return; await cargarLeads(); if (C.sel) await cargarMensajes(C.sel, true); pintar(); }, 15000);
    pintar();
  }
  const cargarLeads = async () => { C.leads = await api("/api/hub/leads").catch(() => C.leads); };
  const cargarCatalogo = async () => { C.items = await api("/api/hub/catalogo").catch(() => C.items); };
  async function cargarMensajes(id, silencioso) { try { C.msgs = await api(`/api/hub/leads/${encodeURIComponent(id)}/mensajes`); } catch (e) { if (!silencioso) aviso(e.message, true); } }

  function pintar() {
    if (!C.me) return pantallaLogin();
    const caja = marco();
    caja.replaceChildren(C.vista === "pipeline" ? vistaPipeline() : C.vista === "catalog" ? vistaCatalogo() : vistaAjustes());
  }

  // ---------------- pipeline ----------------
  function vistaPipeline() {
    const cols = Object.keys(TX.es.cols).map((k) => {
      const enCol = C.leads.filter((l) => l.columna === k);
      return el("div", { class: "col" }, el("h3", {}, x("cols")[k], el("span", { class: "n" }, enCol.length)),
        ...enCol.map((l) => el("button", { class: "lead" + (C.sel === l.sender_id ? " live" : "") + (l.alerta ? " hot" : ""), onclick: async () => { C.sel = l.sender_id; await cargarMensajes(l.sender_id); pintar(); } },
          el("b", {}, l.nombre || l.telefono), el("small", {}, [l.channel, l.lang && l.lang.toUpperCase(), l.budget ? dinero(l.budget) : null].filter(Boolean).join(" · ")),
          l.alerta ? el("span", { class: "tag bad" }, "⚠ " + x("alert")[l.alerta]) : null, l.paused ? el("span", { class: "tag" }, "⏸") : null)));
    });
    return el("div", { class: "crm-pipeline" }, el("div", { class: "board" }, cols), panelConversacion());
  }

  function panelConversacion() {
    const l = C.leads.find((y) => y.sender_id === C.sel);
    if (!l) return el("aside", { class: "panel crm-chat" }, el("p", { class: "muted pad" }, C.leads.length ? x("pick") : x("empty")));
    const caja = el("textarea", { id: "crm-msg", rows: 2, placeholder: x("write"), maxlength: 1500 });
    const comando = (nombre) => async () => {
      try { const r = await api(`/api/hub/leads/${encodeURIComponent(l.sender_id)}/comando`, { method: "POST", body: JSON.stringify({ comando: nombre }) }); aviso(r.resultado || "✓"); }
      catch (e) { aviso(e.message, true); }
      await cargarLeads(); pintar();
    };
    const hilo = el("div", { class: "crm-thread", id: "crm-thread" }, ...C.msgs.map((m) => el("div", { class: `msg ${m.origen === "cliente" ? "in" : "out"} o-${m.origen}` },
      el("div", { class: "who" }, x("origin")[m.origen] || m.origen, m.motor ? el("span", { class: "engine" }, m.motor) : null, el("time", {}, fecha(m.fecha))),
      el("div", { class: "txt" }, m.texto))));
    setTimeout(() => { hilo.scrollTop = hilo.scrollHeight; }, 0);
    return el("aside", { class: "panel crm-chat" },
      el("h2", {}, `${l.nombre || l.telefono}`, el("small", { class: "muted" }, ` ${l.telefono} · ${l.stage}${l.producto ? " · " + l.producto : ""}`)),
      el("div", { class: "controls pad" }, ...Object.keys(TX.es.cmds).map((c) => el("button", { class: "btn small", onclick: comando(c) }, x("cmds")[c]))),
      hilo,
      el("form", { class: "crm-send", onsubmit: async (e) => {
        e.preventDefault(); const texto = caja.value.trim(); if (!texto) return;
        try { await api(`/api/hub/leads/${encodeURIComponent(l.sender_id)}/comando`, { method: "POST", body: JSON.stringify({ mensaje: texto }) }); caja.value = ""; aviso(x("saved")); }
        catch (err) { aviso(err.message, true); }
        await cargarMensajes(l.sender_id); await cargarLeads(); pintar();
      } }, caja, el("button", { class: "btn primary small", type: "submit" }, x("send"))));
  }

  // ---------------- catalog ----------------
  function vistaCatalogo() {
    const cab = el("div", { class: "controls" }, esAdmin() ? el("button", { class: "btn primary small", onclick: () => { C.editando = { nuevo: true, currency: "USD", status: "available", qualification_mode: "credito_inicial", min_down_payment_pct: 10, recommended_down_payment_pct: 20, annual_rate_pct: 0, max_term_years: 1 }; pintar(); } }, x("newItem")) : el("span", { class: "muted" }, x("readonly")),
      C.estado.crm_type !== "peruptd_native" && esAdmin() ? el("button", { class: "btn small", onclick: async () => { try { const r = await api("/api/hub/catalogo/sincronizar", { method: "POST" }); aviso(`⟳ ${r.items} · ${r.media}`); await cargarCatalogo(); pintar(); } catch (e) { aviso(e.message, true); } } }, x("sync")) : null);
    const lista = el("div", { class: "crm-items" }, ...C.items.map((it) => el("article", { class: "panel crm-item" },
      el("h3", {}, it.name_es, it.name_en ? el("small", { class: "muted" }, " / " + it.name_en) : null),
      el("p", {}, `${dinero(it.list_price)} · ${C.lang === "es" ? "contado" : "cash"} ${dinero(it.cash_price)} · ${MODOS[it.qualification_mode || "credito_inicial"][C.lang]}`),
      el("p", { class: "muted" }, `${(it.media || []).length} ${x("files").toLowerCase()} · ${it.status}`),
      el("div", { class: "controls" }, el("button", { class: "btn small", onclick: () => { C.editando = JSON.parse(JSON.stringify(it)); pintar(); } }, esAdmin() ? "✏️" : "👁"),
        esAdmin() ? el("button", { class: "btn small", onclick: async () => { if (!confirm(x("confirmDel"))) return; try { await api(`/api/hub/catalogo/${it.id}`, { method: "DELETE" }); await cargarCatalogo(); pintar(); } catch (e) { aviso(e.message, true); } } }, x("del")) : null))));
    return el("div", {}, cab, C.editando ? formularioItem(C.editando) : null, lista);
  }

  function formularioItem(it) {
    const campo = (k, etiqueta, tipo = "text", extra = {}) => el("label", {}, etiqueta,
      el(tipo === "area" ? "textarea" : "input", { ...(tipo === "area" ? {} : { type: tipo, value: it[k] ?? "" }), ...extra, "data-k": k, disabled: !esAdmin() }, tipo === "area" ? it[k] || "" : null));
    const sel = (k, etiqueta, opciones) => el("label", {}, etiqueta, el("select", { "data-k": k, disabled: !esAdmin() }, ...opciones.map(([v, t]) => el("option", { value: v, selected: it[k] === v }, t))));
    const preguntas = (it.filter_questions || []).map((p) => `${p.es || ""} | ${p.en || ""}`).join("\n");
    const L = C.lang === "es";
    const form = el("form", { class: "panel crm-form", onsubmit: async (e) => {
      e.preventDefault();
      const d = {};
      form.querySelectorAll("[data-k]").forEach((i) => { d[i.dataset.k] = i.type === "number" ? (i.value === "" ? null : Number(i.value)) : i.value; });
      d.keywords = d.keywords || "";
      d.filter_questions = (d.filter_questions || "").split("\n").map((s) => s.split("|")).filter((p) => (p[0] || "").trim()).map(([es, en]) => ({ es: es.trim(), en: (en || "").trim() }));
      try {
        if (it.nuevo) await api("/api/hub/catalogo", { method: "POST", body: JSON.stringify(d) });
        else await api(`/api/hub/catalogo/${it.id}`, { method: "PUT", body: JSON.stringify(d) });
        aviso(x("saved")); C.editando = it.nuevo ? null : C.editando; await cargarCatalogo();
        if (!it.nuevo) C.editando = JSON.parse(JSON.stringify(C.items.find((y) => y.id === it.id) || it));
        pintar();
      } catch (err) { aviso(err.message, true); }
    } },
      el("h3", {}, it.nuevo ? x("newItem").replace("+ ", "") : it.name_es),
      el("div", { class: "grid" },
        campo("name_es", L ? "Nombre (ES)" : "Name (ES)", "text", { required: true, maxlength: 200 }), campo("name_en", L ? "Nombre (EN)" : "Name (EN)"),
        campo("category", L ? "Categoría" : "Category"), sel("status", L ? "Estado" : "Status", [["available", L ? "Disponible" : "Available"], ["last_units", L ? "Últimas unidades" : "Last units"], ["sold_out", L ? "Agotado" : "Sold out"]]),
        campo("list_price", L ? "Precio de lista" : "List price", "number", { step: "0.01", min: 0, required: true }), campo("cash_price", L ? "Precio contado" : "Cash price", "number", { step: "0.01", min: 0 }),
        campo("currency", L ? "Moneda" : "Currency", "text", { maxlength: 3 }), sel("qualification_mode", L ? "Modo de calificación" : "Qualification mode", Object.entries(MODOS).map(([k, v]) => [k, v[C.lang]])),
        campo("min_down_payment_pct", L ? "Inicial mínima %" : "Min down %", "number", { step: "0.1", min: 0, max: 100 }), campo("recommended_down_payment_pct", L ? "Inicial recomendada %" : "Rec. down %", "number", { step: "0.1", min: 0, max: 100 }),
        campo("annual_rate_pct", L ? "Tasa anual %" : "APR %", "number", { step: "0.01", min: 0, max: 100 }), campo("max_term_years", L ? "Plazo máx. (años)" : "Max term (yrs)", "number", { step: "1", min: 0, max: 40 }),
        campo("keywords", L ? "Palabras clave (coma)" : "Keywords (comma)", "text", { value: (it.keywords || []).join(", ") })),
      el("div", { class: "grid two" },
        campo("filter_questions", L ? "Preguntas filtro (una por línea: ES | EN)" : "Filter questions (one per line: ES | EN)", "area"),
        campo("conditions_es", L ? "Condiciones (ES)" : "Conditions (ES)", "area"), campo("conditions_en", L ? "Condiciones (EN)" : "Conditions (EN)", "area"),
        campo("promo_bonus_es", L ? "Bono / promo (ES)" : "Promo (ES)", "area"), campo("promo_bonus_en", L ? "Bono / promo (EN)" : "Promo (EN)", "area"),
        campo("value_comparison_es", L ? "Argumento de valor (ES)" : "Value argument (ES)", "area"), campo("value_comparison_en", L ? "Argumento de valor (EN)" : "Value argument (EN)", "area"),
        campo("insurance_es", L ? "Seguros aceptados (ES)" : "Insurance accepted (ES)", "area"), campo("insurance_en", L ? "Seguros aceptados (EN)" : "Insurance accepted (EN)", "area"),
        campo("location_address", L ? "Dirección" : "Address"), campo("google_maps_url", "Google Maps URL", "url")),
      el("div", { class: "controls" }, esAdmin() ? el("button", { class: "btn primary small", type: "submit" }, x("save")) : null,
        el("button", { class: "btn small", type: "button", onclick: () => { C.editando = null; pintar(); } }, x("cancel"))),
      it.nuevo ? null : archivos(it));
    form.querySelector('[data-k="filter_questions"]').value = preguntas;
    form.querySelector('[data-k="keywords"]').value = (it.keywords || []).join(", ");
    return form;
  }

  function archivos(it) {
    const rol = el("select", { id: "crm-role", "aria-label": x("role") }, ...ROLES.map((r) => el("option", { value: r }, r)));
    const archivo = el("input", { type: "file", id: "crm-file", accept: "image/jpeg,image/png,image/webp,application/pdf,video/mp4,video/quicktime" });
    const leyenda = el("input", { type: "text", id: "crm-caption", placeholder: x("caption"), maxlength: 500 });
    const subir = async () => {
      if (!archivo.files[0]) return;
      const fd = new FormData(); fd.append("file", archivo.files[0]); fd.append("role", rol.value); fd.append(C.lang === "es" ? "caption_es" : "caption_en", leyenda.value);
      try { await api(`/api/hub/catalogo/${it.id}/media`, { method: "POST", body: fd }); aviso(x("saved")); await cargarCatalogo(); C.editando = JSON.parse(JSON.stringify(C.items.find((y) => y.id === it.id))); pintar(); }
      catch (e) { aviso(e.message, true); }
    };
    return el("section", { class: "crm-media" }, el("h4", {}, x("files")),
      (it.media || []).length ? el("ul", {}, ...it.media.map((m) => el("li", {}, el("span", { class: "tag" }, m.trigger_moment), " ",
        el("a", { href: m.file_url, target: "_blank", rel: "noopener" }, m.caption_es || m.caption_en || m.media_type), " ",
        esAdmin() ? el("button", { class: "btn tiny", type: "button", onclick: async () => { try { await api(`/api/hub/catalogo/${it.id}/media/${m.id}`, { method: "DELETE" }); await cargarCatalogo(); C.editando = JSON.parse(JSON.stringify(C.items.find((y) => y.id === it.id))); pintar(); } catch (e) { aviso(e.message, true); } } }, "✕") : null)))
        : el("p", { class: "muted" }, x("noFiles")),
      esAdmin() ? el("div", { class: "controls" }, el("label", {}, x("role"), rol), archivo, leyenda, el("button", { class: "btn small", type: "button", onclick: subir }, x("upload"))) : null);
  }

  // ---------------- settings ----------------
  function vistaAjustes() {
    const caja = el("div", { class: "muted" }, "…");
    (C.ajustes ? Promise.resolve(C.ajustes) : api("/api/hub/playbook")).then((a) => { C.ajustes = a; caja.replaceWith(formAjustes(a)); }).catch((e) => { caja.textContent = e.message; });
    return caja;
  }

  function formAjustes(a) {
    const L = C.lang === "es"; const ro = !esAdmin();
    const inp = (id, valor, extra = {}) => el("input", { id, value: valor ?? "", disabled: ro, ...extra });
    const seg = ["es", "en"].map((idi) => el("details", {}, el("summary", {}, (L ? "Textos de seguimiento " : "Follow-up texts ") + idi.toUpperCase()),
      ...Object.entries(a.seguimiento[idi]).map(([k, v]) => el("label", {}, k, el("textarea", { "data-seg": `${idi}.${k}`, rows: 3, disabled: ro }, v)))));
    const form = el("form", { class: "panel crm-form", onsubmit: async (e) => {
      e.preventDefault();
      const d = { owner_whatsapp: $("#s-owner").value, bot_name: $("#s-bot").value, advisor_name: $("#s-adv").value, address: $("#s-addr").value,
        default_language: $("#s-lang").value, quiet_hours: { start: $("#s-q1").value, end: $("#s-q2").value },
        visiting_hours: { inicio: $("#s-v1").value, fin: $("#s-v2").value, dias: DIAS.filter((dd) => $(`#s-d-${dd}`).checked) },
        forbidden_phrases: $("#s-forb").value, seguimiento: { es: {}, en: {} } };
      form.querySelectorAll("[data-seg]").forEach((t) => { const [idi, k] = t.dataset.seg.split("."); if (t.value !== a.seguimiento[idi][k]) d.seguimiento[idi][k] = t.value; });
      if ($("#s-map")) { try { d.crm_field_mapping = JSON.parse($("#s-map").value || "{}"); } catch (err) { return aviso("JSON: " + err.message, true); } }
      try { C.ajustes = await api("/api/hub/playbook", { method: "PUT", body: JSON.stringify(d) }); aviso(x("saved")); pintar(); } catch (err) { aviso(err.message, true); }
    } },
      el("h3", {}, x("settings"), ro ? el("small", { class: "muted" }, " — " + x("readonly")) : null),
      el("div", { class: "grid" },
        el("label", {}, L ? "WhatsApp del dueño (alertas)" : "Owner WhatsApp (alerts)", inp("s-owner", a.owner_whatsapp, { placeholder: "51987654321" })),
        el("label", {}, L ? "Nombre del agente" : "Agent name", inp("s-bot", a.bot_name)), el("label", {}, L ? "Asesor" : "Advisor", inp("s-adv", a.advisor_name)),
        el("label", {}, L ? "Dirección" : "Address", inp("s-addr", a.address)),
        el("label", {}, L ? "Idioma por defecto" : "Default language", el("select", { id: "s-lang", disabled: ro }, ...["es", "en"].map((l) => el("option", { value: l, selected: a.default_language === l }, l.toUpperCase())))),
        el("label", {}, L ? "Visitas desde" : "Visits from", inp("s-v1", a.visiting_hours.inicio, { type: "time" })), el("label", {}, L ? "hasta" : "until", inp("s-v2", a.visiting_hours.fin, { type: "time" })),
        el("label", {}, L ? "Silencio nocturno desde" : "Quiet hours from", inp("s-q1", a.quiet_hours.start, { type: "time" })), el("label", {}, L ? "hasta" : "until", inp("s-q2", a.quiet_hours.end, { type: "time" }))),
      el("fieldset", { class: "dias" }, el("legend", {}, L ? "Días de visita" : "Visit days"),
        ...DIAS.map((dd) => el("label", {}, el("input", { type: "checkbox", id: `s-d-${dd}`, checked: a.visiting_hours.dias.includes(dd), disabled: ro }), " ", dd))),
      el("label", {}, L ? "Frases prohibidas (una por línea)" : "Forbidden phrases (one per line)", el("textarea", { id: "s-forb", rows: 4, disabled: ro }, a.forbidden_phrases.join("\n"))),
      ...seg,
      a.crm_type !== "peruptd_native" ? el("details", {}, el("summary", {}, (L ? "Mapeo de campos del CRM " : "CRM field mapping ") + `(${a.crm_type})`),
        el("textarea", { id: "s-map", rows: 12, class: "mono", disabled: ro }, JSON.stringify(a.crm_field_mapping, null, 2))) : null,
      esAdmin() ? el("div", { class: "controls" }, el("button", { class: "btn primary small", type: "submit" }, x("save"))) : null);
    return form;
  }

  async function iniciar() {
    marco();
    try { await cargar(); } catch (e) { pantallaLogin(); }
  }
  return { iniciar, C };
})();

// /app (served by Flask, no ?demo=1) = production CRM; anything else = recording demo.
const MODO_CRM = /^https?:/.test(location.protocol) && /\/app\/?$/.test(location.pathname) && !new URLSearchParams(location.search).has("demo");
