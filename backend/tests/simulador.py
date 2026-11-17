"""Simulador de conversaciones completas para pruebas: base de datos en memoria (en lugar de Supabase),
Calendar con agenda libre y WhatsApp sin envíos reales. Permite reproducir chats reales turno por turno."""
import os
import sys
from unittest import mock

os.environ.pop("SUPABASE_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
os.environ["TIPO_CAMBIO_AUTO"] = "false"
os.environ["VISITAS_DESDE"] = ""  # sin fecha de apertura en las pruebas (se prueba aparte con mock)


class _Resultado:
    def __init__(self, data):
        self.data = data


class _Consulta:
    def __init__(self, db, tabla):
        self.db, self.tabla = db, tabla
        self.filtros, self.orden, self.limite, self.op, self.payload = [], None, None, "select", None

    def select(self, *_a, **_k):
        return self

    def eq(self, campo, valor):
        self.filtros.append(lambda r: r.get(campo) == valor)
        return self

    def gte(self, campo, valor):
        self.filtros.append(lambda r: (r.get(campo) or "") >= valor)
        return self

    def in_(self, campo, valores):
        self.filtros.append(lambda r: r.get(campo) in valores)
        return self

    def order(self, campo, desc=False):
        self.orden = (campo, desc)
        return self

    def limit(self, n):
        self.limite = n
        return self

    def insert(self, filas):
        self.op, self.payload = "insert", filas if isinstance(filas, list) else [filas]
        return self

    def upsert(self, fila, on_conflict=None):
        self.op, self.payload, self.clave = "upsert", fila, on_conflict
        return self

    def update(self, cambios):
        self.op, self.payload = "update", cambios
        return self

    def execute(self):
        filas = self.db.setdefault(self.tabla, [])
        if self.op == "insert":
            for f in self.payload:
                f = dict(f)
                f.setdefault("created_at", self.db["_reloj"]())
                filas.append(f)
            return _Resultado(self.payload)
        if self.op == "upsert":
            for f in filas:
                if f.get(self.clave) == self.payload.get(self.clave):
                    f.update(self.payload)
                    return _Resultado([f])
            filas.append(dict(self.payload))
            return _Resultado([self.payload])
        sel = [f for f in filas if all(c(f) for c in self.filtros)]
        if self.op == "update":
            for f in sel:
                f.update(self.payload)
            return _Resultado(sel)
        if self.orden:
            sel = sorted(sel, key=lambda r: r.get(self.orden[0]) or "", reverse=self.orden[1])
        if self.limite:
            sel = sel[: self.limite]
        return _Resultado([dict(f) for f in sel])


class SupabaseFalso:
    def __init__(self):
        self._n = 0
        self.db = {"_reloj": self._reloj}

    def _reloj(self):
        self._n += 1
        return f"2026-11-08T00:00:{self._n:06d}+00:00"

    def table(self, nombre):
        return _Consulta(self.db, nombre)


def _evento_falso(nombre, tel, iso, notas=""):
    import bot.integraciones.calendario as cal
    return True, cal.format_fecha_es(cal.datetime.fromisoformat(iso), relativo=True), "ev-test"


class Simulador:
    """with Simulador() as sim: sim.cliente("PE.123", "Linn", "hola") -> texto que respondió el bot."""

    def __enter__(self):
        import bot.app  # noqa: F401  (importa todos los módulos antes de simular)
        import bot.conversacion.orquestador  # noqa: F401
        import bot.integraciones.calendario as cal
        self.sb = SupabaseFalso()
        self.enviados = []
        self.alertas = []
        self.eventos = []
        self.patches = []
        for nombre, mod in list(sys.modules.items()):
            if nombre.startswith("bot.") and mod is not None:
                if hasattr(mod, "supabase"):
                    self.patches.append(mock.patch.object(mod, "supabase", self.sb))
                if hasattr(mod, "alertar_asesor"):
                    self.patches.append(mock.patch.object(mod, "alertar_asesor", lambda t, *a: self.alertas.append(t)))
                if hasattr(mod, "create_calendar_event"):
                    self.patches.append(mock.patch.object(mod, "create_calendar_event", side_effect=self._crear))
                for fn in ("send_wa_text", "send_wa_media", "send_wa_template"):
                    if hasattr(mod, fn):
                        self.patches.append(mock.patch.object(mod, fn, side_effect=lambda *a, _f=fn: self.enviados.append((_f, a)) or True))
        self.patches.append(mock.patch.object(cal, "get_busy_intervals", lambda a, b: []))
        for p in self.patches:
            p.start()
        return self

    def _crear(self, *a, **k):
        self.eventos.append(a)
        return _evento_falso(*a, **k)

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()

    def cliente(self, sender, nombre, texto):
        from bot.conversacion.orquestador import process_conversation
        res = process_conversation(sender, "whatsapp", texto, nombre)
        parsed = res[0] if isinstance(res, tuple) else res
        return "" if parsed.get("_no_responder") else (parsed.get("reply_text") or "")

    def meta(self, sender):
        import json
        for f in self.sb.db.get("leads", []):
            if f.get("sender_id") == sender:
                return json.loads(f.get("interes") or "{}")
        return {}
