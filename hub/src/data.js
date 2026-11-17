// ===== Demo data: tenants, catalog (bilingual), media library, seeded pipeline and scripted scenarios =====
const INDUSTRIES = {
  realestate: {
    icon: "🏗️", name: { en: "Real Estate / Developer", es: "Inmobiliaria / Constructora" },
    company: "Santa Teresa Homes", advisor: "Henry Sague", botName: { en: "Ava", es: "Ava" },
    location: { en: "Urb. Santa Teresa, Chiclayo — Lot 14", es: "Urb. Santa Teresa, Chiclayo — Lote 14" },
    mapsUrl: "maps.google.com/?q=Santa+Teresa+Chiclayo",
    eventWord: { en: "Showing", es: "Visita" },
    stages: ["new", "qualified", "booked", "visited", "negotiation", "won"],
    items: [
      { id: "re1", external: { salesforce: "01t5g00000Kx3AA", hubspot: "prod_88412", pipedrive: "prd_17", zoho: "ZP-2201", native: "cat_0001" },
        name: { en: "3-Story House — 4BR (Unit A)", es: "Casa de 3 pisos — 4 dorm. (Unidad A)" }, keywords: ["casa", "house", "3br", "3-bedroom", "4br", "unit", "unidad", "ksa", "home", "townhome"],
        category: { en: "Houses", es: "Casas" }, status: "last_units",
        specs: { en: { "Lot": "80 m² (861 sqft)", "Built area": "200 m² (2,153 sqft)", "Floors": "3", "Bedrooms": "4", "Parking": "1 garage" },
                 es: { "Terreno": "80 m²", "Construidos": "200 m²", "Pisos": "3", "Dormitorios": "4", "Cochera": "1" } },
        list_price: 135000, cash_price: 129000, currency: "USD", min_down_pct: 10, rec_down_pct: 20, annual_rate_pct: 8.9, max_term_years: 20,
        promo: { en: "Launch bonus: 1st unit includes installed kitchen cabinets", es: "Bono de lanzamiento: la 1ra unidad incluye reposteros de cocina instalados" },
        value: { en: "At $645/m² you're ~22% below the $830/m² area average — with garage and private yard", es: "A US$645/m² estás ~22% por debajo del promedio de la zona (US$830/m²), con cochera y patio propio" },
        media: [
          { id: "m1", type: "image", trigger: "FIRST_INFO", caption: { en: "Facade at sunset", es: "Fachada al atardecer" }, hue: 24 },
          { id: "m2", type: "image", trigger: "FIRST_INFO", caption: { en: "Living & dining room", es: "Sala comedor" }, hue: 38 },
          { id: "m3", type: "pdf", trigger: "SPECS_PDF", caption: { en: "Floor plans — 3 levels.pdf", es: "Planos — 3 niveles.pdf" }, hue: 210 },
          { id: "m4", type: "image", trigger: "PRICE_OBJECTION", caption: { en: "Garage + private yard", es: "Cochera + patio propio" }, hue: 140 },
          { id: "m5", type: "image", trigger: "LOCATION_FACADE", caption: { en: "Street view + map pin", es: "Vista de calle + ubicación" }, hue: 190 },
          { id: "m6", type: "image", trigger: "POST_VISIT_45M", caption: { en: "Kitchen render — Graphite", es: "Render cocina — Grafito" }, hue: 260 },
          { id: "m7", type: "video", trigger: "VIDEO_TOUR", caption: { en: "Full walkthrough (2:14)", es: "Recorrido completo (2:14)" }, hue: 330 }
        ] },
      { id: "re2", external: { salesforce: "01t5g00000Kx3AB", hubspot: "prod_88413", pipedrive: "prd_18", zoho: "ZP-2202", native: "cat_0002" },
        name: { en: "2BR Apartment — 3rd floor", es: "Departamento 2 dorm. — 3er piso" }, keywords: ["depa", "departamento", "apartment", "apt", "2br", "2-bedroom", "flat"],
        category: { en: "Apartments", es: "Departamentos" }, status: "available",
        specs: { en: { "Area": "68 m² (732 sqft)", "Bedrooms": "2", "Bathrooms": "2", "Balcony": "Yes" }, es: { "Área": "68 m²", "Dormitorios": "2", "Baños": "2", "Balcón": "Sí" } },
        list_price: 89000, cash_price: 85000, currency: "USD", min_down_pct: 10, rec_down_pct: 20, annual_rate_pct: 8.9, max_term_years: 20,
        promo: { en: "Free parking space for the first 3 buyers", es: "Estacionamiento gratis para los 3 primeros compradores" },
        value: { en: "Same finishes as the houses at 34% less", es: "Mismos acabados que las casas por 34% menos" },
        media: [
          { id: "m8", type: "image", trigger: "FIRST_INFO", caption: { en: "Balcony view", es: "Vista desde el balcón" }, hue: 200 },
          { id: "m9", type: "pdf", trigger: "SPECS_PDF", caption: { en: "Apartment plan.pdf", es: "Plano depa.pdf" }, hue: 215 }
        ] }
    ],
    scenarios: {
      es: { label: "4 mensajes cortados con jerga", parts: ["ola q tal", "a cuanto sale la ksa al cntado??", "ta medio salado ah tngo 25 mil nomas", "se podra ver mñn saliendo de la chamba tipo 6 y media?"] },
      en: { label: "SMS burst with slang", parts: ["yo", "hm for the 3br unit?", "ngl sounds steep, only got 25k down", "can i tour tmrw after work round 6?"] }
    },
    quick: { es: ["mándame los planos xfa", "dnd queda?", "tienen video del recorrido?", "sigue caro hno"], en: ["send me the floor plans pls", "wheres it located?", "got a video tour?", "still too steep tbh"] },
    seed: [
      { name: "Lucía Paredes", stage: "qualified", lang: "es", channel: "WhatsApp", pay: "FINANCING", budget: 30000, obj: 1 },
      { name: "Mark Johnson", stage: "booked", lang: "en", channel: "SMS", pay: "CASH", budget: 130000, obj: 0, day: 0 },
      { name: "Rosa Chávez", stage: "visited", lang: "es", channel: "Meta Lead Ad", pay: "FINANCING", budget: 27000, obj: 2, day: 2 },
      { name: "Daniel Ortiz", stage: "negotiation", lang: "es", channel: "Instagram DM", pay: "CASH", budget: 129000, obj: 1, day: 10 },
      { name: "Emily Carter", stage: "new", lang: "en", channel: "Meta Lead Ad", pay: null, budget: null, obj: 0 },
      { name: "Jorge Ramos", stage: "won", lang: "es", channel: "WhatsApp", pay: "CASH", budget: 129000, obj: 1, day: 14 }
    ]
  },
  dental: {
    icon: "🦷", name: { en: "Dental & MedSpa Clinic", es: "Clínica Dental & MedSpa" },
    company: "BrightSmile Dental Studio", advisor: "Dr. Laura Kim", botName: { en: "Mia", es: "Mía" },
    location: { en: "820 Brickell Ave, Miami FL — Suite 400", es: "820 Brickell Ave, Miami FL — Suite 400" },
    mapsUrl: "maps.google.com/?q=820+Brickell+Ave",
    eventWord: { en: "Consultation", es: "Evaluación" },
    stages: ["new", "qualified", "booked", "visited", "negotiation", "won"],
    items: [
      { id: "dn1", external: { salesforce: "01t5g00000Dn1AA", hubspot: "prod_55120", pipedrive: "prd_41", zoho: "ZP-5101", native: "cat_0101" },
        name: { en: "Full-Arch Implants (All-on-4) package", es: "Paquete Implantes de Arcada Completa (All-on-4)" }, keywords: ["implant", "implants", "implante", "implantes", "arcada", "arch", "all-on-4", "pkg", "package", "paquete"],
        category: { en: "Implants", es: "Implantes" }, status: "available",
        specs: { en: { "Procedure": "1 day (sedation)", "Recovery": "48–72 h", "Warranty": "Lifetime on implants", "Visits": "3" }, es: { "Procedimiento": "1 día (con sedación)", "Recuperación": "48–72 h", "Garantía": "De por vida en implantes", "Citas": "3" } },
        list_price: 18500, cash_price: 16900, currency: "USD", min_down_pct: 10, rec_down_pct: 20, annual_rate_pct: 9.9, max_term_years: 3,
        promo: { en: "Free 3D CT scan + consultation this month", es: "Tomografía 3D + evaluación gratis este mes" },
        value: { en: "Avg. Miami price is $23,900 per arch — ours includes the final zirconia teeth", es: "En Miami el promedio es US$23,900 por arcada — el nuestro incluye los dientes finales de zirconio" },
        insurance: { en: "We accept PPO plans (Delta Dental, Cigna, MetLife) — HMO doesn't cover implants", es: "Aceptamos seguros PPO (Delta Dental, Cigna, MetLife) — los HMO no cubren implantes" },
        media: [
          { id: "d1", type: "image", trigger: "FIRST_INFO", caption: { en: "Real patient — before / after", es: "Paciente real — antes / después" }, hue: 190 },
          { id: "d2", type: "pdf", trigger: "SPECS_PDF", caption: { en: "Treatment guide.pdf", es: "Guía del tratamiento.pdf" }, hue: 210 },
          { id: "d3", type: "image", trigger: "PRICE_OBJECTION", caption: { en: "Zirconia vs acrylic (what you get)", es: "Zirconio vs acrílico (lo que recibes)" }, hue: 170 },
          { id: "d4", type: "image", trigger: "LOCATION_FACADE", caption: { en: "Clinic reception", es: "Recepción de la clínica" }, hue: 320 },
          { id: "d5", type: "video", trigger: "VIDEO_TOUR", caption: { en: "Dr. Kim explains the procedure (1:40)", es: "La Dra. Kim explica el procedimiento (1:40)" }, hue: 280 }
        ] },
      { id: "dn2", external: { salesforce: "01t5g00000Dn1AB", hubspot: "prod_55121", pipedrive: "prd_42", zoho: "ZP-5102", native: "cat_0102" },
        name: { en: "Clear aligners (full case)", es: "Alineadores invisibles (caso completo)" }, keywords: ["aligner", "aligners", "invisalign", "alineadores", "braces", "brackets"],
        category: { en: "Orthodontics", es: "Ortodoncia" }, status: "available",
        specs: { en: { "Duration": "6–14 months", "Visits": "Every 8 weeks" }, es: { "Duración": "6–14 meses", "Controles": "Cada 8 semanas" } },
        list_price: 4800, cash_price: 4400, currency: "USD", min_down_pct: 10, rec_down_pct: 20, annual_rate_pct: 0, max_term_years: 1,
        promo: { en: "0% financing for 12 months", es: "0% de interés a 12 meses" },
        value: { en: "Includes whitening and retainers", es: "Incluye blanqueamiento y retenedores" },
        media: [ { id: "d6", type: "image", trigger: "FIRST_INFO", caption: { en: "Aligner smile result", es: "Resultado con alineadores" }, hue: 200 } ] }
    ],
    scenarios: {
      es: { label: "Mensajes con jerga y cuotas", parts: ["holi buenas", "cuanto x los implantes de arcada completa?", "ta salado, tienen cuotas o aceptan seguro?", "puedo el sab tipo 11"] },
      en: { label: "SMS slang + insurance", parts: ["yo hm for the implant pkg?", "ngl sounds steep, yall take delta dental or payment plans?", "free this sat round 4ish"] }
    },
    quick: { es: ["mándame la guía en pdf", "dnd están?", "tienen video del doctor?", "sigue caro"], en: ["send the treatment guide pls", "where r u located?", "got a video from the doctor?", "still pricey tbh"] },
    seed: [
      { name: "Michael Torres", stage: "booked", lang: "en", channel: "Meta Lead Ad", pay: "FINANCING", budget: 3000, obj: 1, day: 0 },
      { name: "Ana Gutiérrez", stage: "qualified", lang: "es", channel: "WhatsApp", pay: "INSURANCE", budget: null, obj: 0 },
      { name: "Sarah Lopez", stage: "visited", lang: "en", channel: "SMS", pay: "CASH", budget: 17000, obj: 0, day: 2 },
      { name: "Carlos Mena", stage: "negotiation", lang: "es", channel: "Instagram DM", pay: "FINANCING", budget: 2000, obj: 2, day: 10 },
      { name: "Jennifer Wu", stage: "new", lang: "en", channel: "Meta Lead Ad", pay: null, budget: null, obj: 0 }
    ]
  },
  b2b: {
    icon: "🏢", name: { en: "B2B Services & Distribution", es: "Servicios B2B & Distribución" },
    company: "Northline Industrial Supply", advisor: "Ryan Patel", botName: { en: "Max", es: "Max" },
    location: { en: "Zoom / on-site at your plant", es: "Zoom / visita en tu planta" },
    mapsUrl: "northline.example/meet",
    eventWord: { en: "Discovery call", es: "Reunión de diagnóstico" },
    stages: ["new", "qualified", "booked", "visited", "negotiation", "won"],
    items: [
      { id: "b1", external: { salesforce: "01t5g00000Bz9AA", hubspot: "prod_77001", pipedrive: "prd_90", zoho: "ZP-9001", native: "cat_0201" },
        name: { en: "Premium Maintenance Plan (monthly)", es: "Servicio Premium de Mantenimiento (mensual)" }, keywords: ["premium", "premiun", "servicio", "service", "plan", "maintenance", "mantenimiento"],
        category: { en: "Service plans", es: "Planes de servicio" }, status: "available",
        specs: { en: { "Response time": "4 h on-site", "Coverage": "Up to 40 machines", "Support": "24/7", "Onboarding": "7 days" }, es: { "Respuesta": "4 h en planta", "Cobertura": "Hasta 40 máquinas", "Soporte": "24/7", "Implementación": "7 días" } },
        list_price: 2400, cash_price: 2150, currency: "USD", min_down_pct: 0, rec_down_pct: 0, annual_rate_pct: 0, max_term_years: 1,
        promo: { en: "Quarter-end: 1st month at 50%", es: "Cierre de trimestre: 1er mes al 50%" },
        value: { en: "Clients cut unplanned downtime ~32% — about $186k/yr saved for a 220-person plant", es: "Nuestros clientes reducen ~32% las paradas no planificadas — unos US$186 mil/año en una planta de 220 personas" },
        media: [
          { id: "b1m", type: "pdf", trigger: "FIRST_INFO", caption: { en: "Premium plan one-pager.pdf", es: "Ficha Plan Premium.pdf" }, hue: 215 },
          { id: "b2m", type: "pdf", trigger: "SPECS_PDF", caption: { en: "SLA & technical sheet.pdf", es: "SLA y ficha técnica.pdf" }, hue: 225 },
          { id: "b3m", type: "image", trigger: "PRICE_OBJECTION", caption: { en: "ROI case — stamping plant", es: "Caso ROI — planta de estampado" }, hue: 150 },
          { id: "b4m", type: "video", trigger: "VIDEO_TOUR", caption: { en: "3-min product demo", es: "Demo del servicio (3 min)" }, hue: 280 }
        ] },
      { id: "b2", external: { salesforce: "01t5g00000Bz9AB", hubspot: "prod_77002", pipedrive: "prd_91", zoho: "ZP-9002", native: "cat_0202" },
        name: { en: "Distribution Platform (annual)", es: "Plataforma de Distribución (anual)" }, keywords: ["platform", "plataforma", "distribution", "distribución", "software", "license", "licencia"],
        category: { en: "Software", es: "Software" }, status: "available",
        specs: { en: { "Users": "Unlimited", "Integrations": "Salesforce, SAP, Odoo", "Implementation": "30 days" }, es: { "Usuarios": "Ilimitados", "Integraciones": "Salesforce, SAP, Odoo", "Implementación": "30 días" } },
        list_price: 24000, cash_price: 21600, currency: "USD", min_down_pct: 25, rec_down_pct: 50, annual_rate_pct: 0, max_term_years: 1,
        promo: { en: "Free migration from spreadsheets", es: "Migración gratis desde Excel" },
        value: { en: "Replaces 3 tools at 40% of the combined cost", es: "Reemplaza 3 herramientas al 40% del costo combinado" },
        media: [ { id: "b5m", type: "pdf", trigger: "FIRST_INFO", caption: { en: "Platform brochure.pdf", es: "Brochure plataforma.pdf" }, hue: 230 } ] }
    ],
    scenarios: {
      es: { label: "Jerga peruana + presupuesto", parts: ["ola hno q tal", "a cuanto sale el srvicio premiun al cntado??", "ta medio salado ah, tngo 2 lucas nomas", "se podra ver mñn saliendo de la chamba tipo 6 y media?"] },
      en: { label: "Buyer shorthand", parts: ["hey", "whats the price on the premium maintenance plan, cash?", "kinda pricey ngl, budget is like 2k", "can we hop on a call tmrw after 5"] }
    },
    quick: { es: ["mándame la ficha técnica", "tienen video demo?", "sigue salado hno", "y la plataforma cuánto?"], en: ["send the SLA sheet pls", "got a demo video?", "still too pricey", "and the platform hm?"] },
    seed: [
      { name: "Sarah Chen", stage: "booked", lang: "en", channel: "Meta Lead Ad", pay: "CASH", budget: 2400, obj: 1, day: 0 },
      { name: "Grupo Andino SAC", stage: "qualified", lang: "es", channel: "WhatsApp", pay: "FINANCING", budget: 20000, obj: 0 },
      { name: "Atlas Mfg.", stage: "negotiation", lang: "en", channel: "SMS", pay: "CASH", budget: 22000, obj: 2, day: 10 },
      { name: "Textiles Norte", stage: "visited", lang: "es", channel: "Instagram DM", pay: "CASH", budget: 2000, obj: 1, day: 5 },
      { name: "Kevin Brooks", stage: "new", lang: "en", channel: "Meta Lead Ad", pay: null, budget: null, obj: 0 }
    ]
  }
};

const CRMS = {
  native: { name: "PeruPTD Native CRM", short: "PeruPTD", color: "#ff5a1f", leadObj: "leads", eventObj: "appointments", catalogSrc: "catalog_items · catalog_media (Supabase Storage)" },
  salesforce: { name: "Salesforce", short: "Salesforce", color: "#0176d3", leadObj: "Lead", eventObj: "Event", catalogSrc: "Product2 · PricebookEntry · ContentVersion" },
  hubspot: { name: "HubSpot", short: "HubSpot", color: "#ff7a59", leadObj: "Contact + Deal", eventObj: "Meeting", catalogSrc: "crm/v3/objects/products · Files" },
  pipedrive: { name: "Pipedrive", short: "Pipedrive", color: "#1a1a1a", leadObj: "Person + Deal", eventObj: "Activity (meeting)", catalogSrc: "Products · Files API" },
  zoho: { name: "Zoho CRM", short: "Zoho", color: "#e42527", leadObj: "Leads", eventObj: "Events", catalogSrc: "Products · Attachments" }
};

const PROTOCOL = [
  { key: "t24", when: { en: "T − 24h", es: "T − 24 h" }, what: { en: "Attendance confirmation", es: "Confirmación de asistencia" } },
  { key: "t75", when: { en: "T + 75 min", es: "T + 75 min" }, what: { en: "Asks the rep: attended / no-show", es: "Pregunta al asesor: vino / no vino" } },
  { key: "t45", when: { en: "+45 min after visit", es: "+45 min tras la visita" }, what: { en: "Post-visit media to review at home", es: "Material para revisar en casa" } },
  { key: "d2", when: { en: "Day 2", es: "Día 2" }, what: { en: "Documents / financing options", es: "Documentos / opciones de pago" } },
  { key: "d5", when: { en: "Day 5", es: "Día 5" }, what: { en: "2nd visit or open questions", es: "2da visita o dudas abiertas" } },
  { key: "d10", when: { en: "Day 10", es: "Día 10" }, what: { en: "Closing bonus + call alert", es: "Bono de cierre + alerta de llamada" } },
  { key: "d14", when: { en: "Day 14", es: "Día 14" }, what: { en: "Release hold & close file", es: "Liberar separación y cerrar ficha" } }
];
