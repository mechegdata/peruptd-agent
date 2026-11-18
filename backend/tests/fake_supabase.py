"""Supabase en memoria para pruebas de la web del CRM: select/eq/order/limit/insert/update/delete/upsert + Storage."""
import copy
import uuid
from types import SimpleNamespace


class _Q:
    def __init__(self, db, nombre):
        self.db, self.nombre, self.filtros, self.op, self.datos = db, nombre, [], "select", None
        self._orden, self._limite, self.conflicto = None, None, None

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def eq(self, c, v):
        self.filtros.append((c, v))
        return self

    def order(self, c, desc=False):
        self._orden = (c, desc)
        return self

    def limit(self, n):
        self._limite = n
        return self

    def insert(self, filas):
        self.op, self.datos = "insert", filas if isinstance(filas, list) else [filas]
        return self

    def upsert(self, filas, on_conflict=None):
        self.op, self.datos, self.conflicto = "upsert", filas if isinstance(filas, list) else [filas], on_conflict
        return self

    def update(self, d):
        self.op, self.datos = "update", d
        return self

    def delete(self):
        self.op = "delete"
        return self

    def _coinciden(self):
        return [f for f in self.db.tablas.setdefault(self.nombre, []) if all(f.get(c) == v for c, v in self.filtros)]

    def execute(self):
        t = self.db.tablas.setdefault(self.nombre, [])
        self.db.log.append((self.nombre, self.op, list(self.filtros)))
        if self.op == "select":
            filas = self._coinciden()
            if self._orden:
                filas = sorted(filas, key=lambda f: (f.get(self._orden[0]) is None, f.get(self._orden[0]) or 0), reverse=self._orden[1])
            return SimpleNamespace(data=copy.deepcopy(filas[: self._limite] if self._limite else filas))
        if self.op == "insert":
            nuevas = [{"id": str(uuid.uuid4()), **f} for f in self.datos]
            t.extend(nuevas)
            return SimpleNamespace(data=copy.deepcopy(nuevas))
        if self.op == "upsert":
            claves = (self.conflicto or "id").split(",")
            salida = []
            for f in self.datos:
                ya = next((x for x in t if all(x.get(k) == f.get(k) for k in claves)), None)
                if ya:
                    ya.update(f)
                    salida.append(ya)
                else:
                    t.append({"id": str(uuid.uuid4()), **f})
                    salida.append(t[-1])
            return SimpleNamespace(data=copy.deepcopy(salida))
        if self.op == "update":
            filas = self._coinciden()
            for f in filas:
                f.update(self.datos)
            return SimpleNamespace(data=copy.deepcopy(filas))
        if self.op == "delete":
            filas = self._coinciden()
            self.db.tablas[self.nombre] = [f for f in t if f not in filas]
            return SimpleNamespace(data=copy.deepcopy(filas))


class _Bucket:
    def __init__(self, db, nombre):
        self.db, self.nombre = db, nombre

    def upload(self, ruta, contenido, opciones=None):
        self.db.archivos[f"{self.nombre}/{ruta}"] = contenido

    def get_public_url(self, ruta):
        return f"https://x.supabase.co/storage/v1/object/public/{self.nombre}/{ruta}"

    def remove(self, rutas):
        for r in rutas:
            self.db.archivos.pop(f"{self.nombre}/{r}", None)


class FakeSupabase:
    def __init__(self, tablas=None):
        self.tablas = copy.deepcopy(tablas or {})
        self.archivos, self.log = {}, []
        self.storage = SimpleNamespace(from_=lambda b: _Bucket(self, b))

    def table(self, nombre):
        return _Q(self, nombre)
