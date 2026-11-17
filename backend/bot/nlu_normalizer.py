"""Capa 1 · Intérprete semántico bilingüe (ES / EN / Spanglish).

Recibe el texto ya agrupado del cliente (jergas, abreviaturas, errores de tipeo, mensajes partidos) y devuelve un
NormalizedTurn validado con pydantic: idioma, texto limpio, intenciones y entidades. La fila de motores determinísticos
trabaja sobre ese JSON, así que ya no depende de que el cliente escriba la palabra exacta.

Estrategia:
  1. Siempre corre el normalizador determinístico (bot/nlu/lexico.py, ~1 ms, sin red).
  2. Si NLU_LLM_ACTIVO y hay llave de Gemini, pide al LLM la misma estructura en JSON estricto con un presupuesto de
     tiempo corto (NLU_PRESUPUESTO_SEG). Si responde a tiempo y valida, se combina con el determinístico.
  3. Si el LLM falla, tarda o devuelve algo inválido, se usa el determinístico. El LLM NUNCA redacta la respuesta al
     cliente aquí: solo clasifica. Precios y condiciones los ponen los motores desde el catálogo."""
import json
import time
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from bot.config import NLU_LLM_ACTIVO, NLU_PRESUPUESTO_SEG
from bot.nlu import lexico

INTENCIONES = {
    "GREETING", "GENERAL_INFO", "PRICE_INQUIRY", "CASH_DISCOUNT", "FINANCING_CALCULATION", "BUDGET_STATEMENT",
    "OBJECTION_EXPENSIVE", "SPECS_AND_PLANS", "LOCATION_INQUIRY", "SCHEDULE_REQUEST", "SLOT_SELECTION", "RESCHEDULE",
    "COURTESY_WAIT", "NOT_INTERESTED", "INSURANCE_INQUIRY", "VIDEO_TOUR",
    "SCHEDULE_AND_PRICE_OBJECTION", "FINANCING_AND_SCHEDULE",   # primarias compuestas
}


class Entities(BaseModel):
    model_config = ConfigDict(extra="ignore")
    service_keyword: Optional[str] = None
    catalog_item_id: Optional[str] = None
    budget_amount: Optional[float] = None
    budget_currency: Optional[str] = None
    payment_type: Optional[Literal["CASH", "FINANCING"]] = None
    insurance: Optional[str] = None
    price_objection: bool = False
    work_end_hour: Optional[str] = None            # "18:00": hora en que sale del trabajo
    work_end_constraint: Optional[str] = None      # alias usado en la documentación comercial
    proposed_date_relative: Optional[str] = None   # TOMORROW | TODAY | THIS_SATURDAY | ...
    proposed_time: Optional[str] = None            # "18:30"
    preferred_days: list[str] = Field(default_factory=list)
    selected_slot_index: Optional[int] = Field(default=None, ge=1, le=3)
    companions: Optional[int] = None

    @model_validator(mode="after")
    def _alias_hora(self):
        self.work_end_hour = self.work_end_hour or self.work_end_constraint
        self.work_end_constraint = self.work_end_constraint or self.work_end_hour
        return self


class NormalizedTurn(BaseModel):
    detected_language: Literal["es", "en"]
    clean_text: str
    regional_slang_detected: list[str] = Field(default_factory=list)
    primary_intent: str
    intents: list[str]
    entities: Entities = Field(default_factory=Entities)
    source: str = "lexicon"
    ms: int = 0

    @model_validator(mode="after")
    def _solo_intenciones_conocidas(self):
        self.intents = [i for i in self.intents if i in INTENCIONES] or ["GENERAL_INFO"]
        if self.primary_intent not in INTENCIONES:
            self.primary_intent = self.intents[0]
        return self

    def tiene(self, *nombres):
        """True si alguna intención (primaria o secundaria) contiene alguno de los nombres."""
        return any(n in i for i in [self.primary_intent, *self.intents] for n in nombres)


_PROMPT = """Eres la Capa 1 (intérprete) de un agente de ventas. NO respondes al cliente: solo traduces su mensaje a JSON.
El cliente puede escribir en español, inglés o Spanglish, con jergas (Perú, México, Colombia, EE. UU.), abreviaturas
de chat ("q tal", "xfa", "hm", "tmrw", "ngl"), errores de tipeo y números en texto ("2 lucas" = 2000, "25k" = 25000).

Devuelve SOLO este JSON (sin texto extra):
{{"detected_language": "es"|"en", "clean_text": "<lo que quiso decir, corregido, en SU idioma>",
 "regional_slang_detected": ["<jerga> (<significado>)"], "primary_intent": "<una>", "intents": ["<todas, en orden>"],
 "entities": {{"service_keyword": str|null, "budget_amount": number|null, "budget_currency": str|null,
   "payment_type": "CASH"|"FINANCING"|null, "insurance": str|null, "price_objection": bool, "work_end_hour": "HH:MM"|null,
   "proposed_date_relative": "TODAY"|"TOMORROW"|"THIS_SATURDAY"|"THIS_SUNDAY"|"MONDAY"|null, "proposed_time": "HH:MM"|null,
   "preferred_days": [str], "selected_slot_index": 1|2|3|null, "companions": int|null}}}}
Intenciones válidas: {intenciones}.
Servicios del catálogo (usa la palabra que dijo el cliente en service_keyword): {catalogo}
Últimos mensajes del chat (contexto): {historial}
Mensaje del cliente: {mensaje}"""


def _catalogo_txt(items):
    return "; ".join(f"{i.get('name_es') or i.get('name')} [{', '.join((i.get('keywords') or [])[:6])}]" for i in (items or [])[:12]) or "—"


class SemanticNormalizer:
    def __init__(self, llamar_llm=None, usar_llm=None, presupuesto_seg=None):
        self.usar_llm = NLU_LLM_ACTIVO if usar_llm is None else usar_llm
        self.presupuesto_seg = presupuesto_seg or NLU_PRESUPUESTO_SEG
        self._llm = llamar_llm

    def _llamar(self, prompt):
        if self._llm:
            return self._llm(prompt, self.presupuesto_seg)
        from bot.ia.gemini import pedir_json
        return pedir_json(prompt, self.presupuesto_seg)

    def normalize(self, texto, items=None, historial=None, idioma_anterior=None):
        t0 = time.time()
        base = lexico.normalizar(texto, items, idioma_anterior)
        turno = NormalizedTurn(**base)
        if self.usar_llm:
            try:
                crudo = self._llamar(_PROMPT.format(intenciones=", ".join(sorted(INTENCIONES)), catalogo=_catalogo_txt(items),
                                                    historial=json.dumps((historial or [])[-6:], ensure_ascii=False), mensaje=texto))
                if crudo:
                    turno = self._combinar(turno, NormalizedTurn(**{**crudo, "source": "llm"}), items)
            except (ValidationError, TypeError, ValueError) as e:
                print("NLU: el LLM devolvió un JSON inválido, se usa el léxico:", str(e)[:200])
            except Exception as e:
                print("NLU: LLM no disponible, se usa el léxico:", str(e)[:200])
        turno.ms = int((time.time() - t0) * 1000)
        return turno

    @staticmethod
    def _combinar(lex, llm, items):
        """El LLM aporta idioma, texto limpio e intenciones; las entidades que el LLM no trae se completan con el léxico.
        El producto del catálogo siempre se resuelve contra el catálogo real (nunca un Id inventado)."""
        ent = lex.entities.model_dump()
        for k, v in llm.entities.model_dump().items():
            if v not in (None, [], False) and k != "catalog_item_id":
                ent[k] = v
        item, clave = lexico._item_mencionado(lexico.sin_tildes(llm.clean_text + " " + (llm.entities.service_keyword or "")), items)
        if item:
            ent.update(catalog_item_id=str(item.get("id")), service_keyword=llm.entities.service_keyword or clave)
        intents = list(dict.fromkeys(llm.intents + [i for i in lex.intents if i not in llm.intents]))
        return NormalizedTurn(detected_language=llm.detected_language, clean_text=llm.clean_text,
                              regional_slang_detected=llm.regional_slang_detected or lex.regional_slang_detected,
                              primary_intent=llm.primary_intent, intents=intents, entities=Entities(**ent), source="llm+lexicon")
