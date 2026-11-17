"""Colas persistentes (migración 002): dedupe que sobrevive reinicios, agrupación en BD y saludo de Lead Ads por /cron."""
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

import bot.agrupador as agrupador
from bot import db
from bot.datos import colas, idempotencia, persistencia
from bot.estado import PROCESSED_IDS


class _ErrorDuplicado(Exception):
    code = "23505"


class _Q:
    def __init__(self, base, tabla):
        self.base, self.tabla, self.f, self.op, self.datos, self.lim = base, tabla, [], "select", None, None

    def select(self, *_):
        return self

    def insert(self, fila):
        self.op, self.datos = "insert", fila
        return self

    def update(self, cambios):
        self.op, self.datos = "update", cambios
        return self

    def delete(self):
        self.op = "delete"
        return self

    def _filtro(self, campo, fn):
        self.f.append(lambda r: r.get(campo) is not None and fn(r.get(campo)))
        return self

    def eq(self, c, v):
        return self._filtro(c, lambda x: x == v)

    def gt(self, c, v):
        return self._filtro(c, lambda x: x > v)

    def lt(self, c, v):
        return self._filtro(c, lambda x: x < v)

    def lte(self, c, v):
        return self._filtro(c, lambda x: x <= v)

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self.lim = n
        return self

    def execute(self):
        filas = self.base.tablas.setdefault(self.tabla, [])
        if self.op == "insert":
            fila = dict(self.datos)
            if self.tabla == "processed_webhooks" and any(r["message_id"] == fila["message_id"] for r in filas):
                raise _ErrorDuplicado("duplicate key value violates unique constraint")
            self.base.n += 1
            fila.setdefault("id", self.base.n)
            fila.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            filas.append(fila)
            return mock.Mock(data=[fila])
        sel = [r for r in filas if all(fn(r) for fn in self.f)]
        if self.op == "update":
            for r in sel:
                r.update(self.datos)
            return mock.Mock(data=[dict(r) for r in sel])
        if self.op == "delete":
            self.base.tablas[self.tabla] = [r for r in filas if r not in sel]
            return mock.Mock(data=sel)
        return mock.Mock(data=[dict(r) for r in sel][: self.lim or None])


class SupabaseConColas:
    def __init__(self):
        self.tablas, self.n = {}, 0

    def table(self, nombre):
        return _Q(self, nombre)


@pytest.fixture
def sb():
    falso = SupabaseConColas()
    persistencia._APAGADO_HASTA["ts"] = 0
    with mock.patch.object(db, "supabase", falso):
        yield falso
    persistencia._APAGADO_HASTA["ts"] = 0


def test_dedupe_sobrevive_reinicio(sb):
    assert idempotencia.ya_procesado("wamid.ABC", "whatsapp") is False
    assert idempotencia.ya_procesado("wamid.ABC", "whatsapp") is True   # mismo proceso
    PROCESSED_IDS.clear()                                                # "reinicio": se pierde la memoria
    assert idempotencia.ya_procesado("wamid.ABC", "whatsapp") is True   # la BD lo recuerda
    assert idempotencia.ya_procesado("wamid.OTRO", "whatsapp") is False


def test_sin_tablas_vuelve_a_memoria():
    class Rota:
        def table(self, _):
            raise RuntimeError("relation \"processed_webhooks\" does not exist")
    persistencia._APAGADO_HASTA["ts"] = 0
    with mock.patch.object(db, "supabase", Rota()):
        assert idempotencia.ya_procesado("wamid.X1") is False
        assert not persistencia.disponible()          # se apaga unos minutos
        assert idempotencia.ya_procesado("wamid.X1") is True   # memoria del proceso
    persistencia._APAGADO_HASTA["ts"] = 0


def test_agrupa_fragmentos_en_bd(sb):
    with mock.patch.object(agrupador.time, "sleep"):
        id1 = colas.encolar_fragmento("51999", "Hola", "whatsapp", "Linn", 15)
        id2 = colas.encolar_fragmento("51999", "¿dónde están?", "whatsapp", "Linn", 6)
        assert colas.reclamar_lote("51999", id1, "Hola") is None             # llegó otro después: responde ese
        assert colas.reclamar_lote("51999", id2, "¿dónde están?") == "Hola\n¿dónde están?"
        assert colas.reclamar_lote("51999", id2, "x") is None                # ya se tomó


def test_esperar_y_agrupar_usa_bd(sb):
    with mock.patch.object(agrupador.time, "sleep"):
        assert agrupador.esperar_y_agrupar("51888", "precio?") == "precio?"
    assert all(f["status"] == "tomado" for f in sb.tablas["debounce_batches"])


def test_cron_toma_lote_vencido_tras_reinicio(sb):
    colas.encolar_fragmento("51777", "Hola", "whatsapp", "Ana", 15)
    colas.encolar_fragmento("51777", "precio", "whatsapp", "Ana", 6)
    for f in sb.tablas["debounce_batches"]:   # la petición murió: ya pasó su hora hace rato
        f["execute_at"] = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    assert colas.lotes_vencidos() == [("51777", "Hola\nprecio", "Ana", "whatsapp")]
    assert colas.lotes_vencidos() == []


def test_leadad_no_se_duplica_entre_timer_y_cron(sb):
    tid = colas.programar_tarea("lead_ad", "51666", {"phone_norm": "51666"}, 90)
    assert colas.reclamar_tarea(tid) is True      # el timer la toma
    assert colas.reclamar_tarea(tid) is False     # /cron (u otra instancia) ya no
    tid2 = colas.programar_tarea("lead_ad", "51555", {"phone_norm": "51555"}, 90)
    sb.tablas["scheduled_jobs"][-1]["execute_at"] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    vencidas = colas.tareas_vencidas("lead_ad")
    assert [f["id"] for f in vencidas] == [tid2]
    assert colas.reclamar_tarea(tid2) is False


def test_reprogramar_cancela_la_anterior(sb):
    colas.programar_tarea("lead_ad", "51444", {}, 90)
    colas.programar_tarea("lead_ad", "51444", {}, 90)
    estados = [f["status"] for f in sb.tablas["scheduled_jobs"]]
    assert estados == ["cancelado", "pending"]
