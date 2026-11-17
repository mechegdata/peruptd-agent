"""Llamada a Gemini (AI Studio / Vertex express) con lista de modelos y presupuesto de tiempo."""
import json
import os
import re
import time

import requests

from bot.config import GEMINI_KEY, GEMINI_MODELS, GEMINI_PRESUPUESTO_SEG, GEMINI_TIMEOUT_MODELO_SEG
from bot.estado import GEMINI_ESTADO


def extract_json_from_llm(raw_text):
    if not raw_text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip()).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


# Las llaves "AIza..." son de Google AI Studio (generativelanguage); las "AQ...." son de Vertex AI en modo express (aiplatform)
GEMINI_ENDPOINTS = {
    "ai_studio": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
    "vertex_express": "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent?key={key}",
}


def _gemini_endpoints():
    forzado = os.environ.get("GEMINI_ENDPOINT", "auto")
    if forzado in GEMINI_ENDPOINTS:
        return [forzado]
    orden = ["vertex_express", "ai_studio"] if (GEMINI_KEY or "").startswith("AQ.") else ["ai_studio", "vertex_express"]
    if GEMINI_ESTADO["endpoint_ok"] in orden:
        orden.remove(GEMINI_ESTADO["endpoint_ok"])
        orden.insert(0, GEMINI_ESTADO["endpoint_ok"])
    return orden


def call_gemini_api(full_prompt):
    # Probamos primero el formato simple compatible al 100% con llaves AQ.Ab8... y gemini-3.8-flash
    simple_payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"temperature": 0.25, "responseMimeType": "application/json"}
    }
    if not GEMINI_KEY:
        print("GEMINI_API_KEY no configurada: se usará el motor de respaldo.")
        return None
    t0 = time.time()
    intentos = [(model, ep) for model in GEMINI_MODELS for ep in _gemini_endpoints()]
    for model, ep in intentos:
        restante = GEMINI_PRESUPUESTO_SEG - (time.time() - t0)
        if restante < 3:
            print(f"Gemini sin tiempo restante ({GEMINI_PRESUPUESTO_SEG}s): se usa el motor de respaldo.")
            break
        try:
            r = requests.post(
                GEMINI_ENDPOINTS[ep].format(model=model, key=GEMINI_KEY),
                json=simple_payload,
                # Un modelo saturado no debe consumir todo el presupuesto: así queda tiempo para el siguiente
                timeout=min(restante, GEMINI_TIMEOUT_MODELO_SEG) if len(GEMINI_MODELS) > 1 else restante
            )
            if r.status_code != 200:
                print(f"Gemini {model} [{ep}] respondió HTTP {r.status_code}: {r.text[:300]}")
                continue
            GEMINI_ESTADO["endpoint_ok"] = ep
            data = r.json()
            if "candidates" in data and data["candidates"]:
                raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                parsed = extract_json_from_llm(raw)
                if parsed and parsed.get("reply_text"):
                    return parsed
                elif raw and not raw.startswith("{"):
                    return {
                        "reply_text": raw,
                        "private_reply": "",
                        "ignorar_comentario": False,
                        "enviar_ficha_tecnica": False,
                        "enviar_renders_cocina": False,
                        "estilo_render_preferido": "ambos",
                        "agendar_visita_iso": ""
                    }
                else:
                    print(f"Gemini {model} devolvió JSON inválido:", raw[:300])
            else:
                print(f"Respuesta sin candidates en {model}:", data)
        except Exception as e:
            print(f"Excepcion llamando a {model}:", e)
            continue
    return None


def pedir_json(prompt, presupuesto_seg=2.0, temperatura=0.1):
    """Llamada corta que devuelve un dict (o None). La usa el NLU de la Capa 1: un solo modelo rápido y poco tiempo,
    porque si no contesta a tiempo el léxico determinístico ya tiene una interpretación lista."""
    if not GEMINI_KEY:
        return None
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": temperatura, "responseMimeType": "application/json"}}
    t0 = time.time()
    for ep in _gemini_endpoints():
        restante = presupuesto_seg - (time.time() - t0)
        if restante <= 0.2:
            return None
        try:
            r = requests.post(GEMINI_ENDPOINTS[ep].format(model=GEMINI_MODELS[0], key=GEMINI_KEY), json=payload, timeout=restante)
        except Exception as e:
            print(f"NLU Gemini [{ep}] sin respuesta a tiempo:", e)
            continue
        if r.status_code != 200:
            continue
        GEMINI_ESTADO["endpoint_ok"] = ep
        try:
            raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, ValueError):
            return None
        return extract_json_from_llm(raw)
    return None
