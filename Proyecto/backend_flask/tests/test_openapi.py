"""La especificación debe describir EXACTAMENTE las rutas que existen (sin documentar de más ni de menos)."""

import re
from pathlib import Path

import yaml

from app import create_app

RAIZ = Path(__file__).resolve().parents[1]


def _operaciones_codigo():
    app = create_app({"TESTING": True})
    ops = set()
    for regla in app.url_map.iter_rules():
        if not regla.rule.startswith("/api/v1"):
            continue
        ruta = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", regla.rule[len("/api/v1") :])
        for m in regla.methods - {"HEAD", "OPTIONS"}:
            ops.add((ruta, m.lower()))
    return ops


def test_openapi_coincide_con_las_rutas(client=None):
    spec = yaml.safe_load((RAIZ / "openapi.yaml").read_text(encoding="utf-8"))
    doc = {(r, m) for r, ms in spec["paths"].items() for m in ms if m in {"get", "post", "patch", "delete", "put"}}
    codigo = _operaciones_codigo()
    assert doc - codigo == set(), f"documentadas pero inexistentes: {sorted(doc - codigo)}"
    assert codigo - doc == set(), f"existen pero sin documentar: {sorted(codigo - doc)}"


def test_openapi_json_disponible(client):
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200 and r.get_json()["openapi"] == "3.0.3"


def test_openapi_documenta_cada_operacion_completa():
    """Cada endpoint: descripción, estado, fuente, ejemplo de respuesta y de solicitud, y errores documentados."""
    spec = yaml.safe_load((RAIZ / "openapi.yaml").read_text(encoding="utf-8"))
    for ruta, metodos in spec["paths"].items():
        for metodo, op in metodos.items():
            if metodo not in {"get", "post", "patch", "delete", "put"}:
                continue
            nombre = f"{metodo.upper()} {ruta}"
            assert op.get("description"), nombre
            assert op.get("x-fuente-datos"), nombre
            assert op.get("x-estado") in {"implementado", "pendiente"}, nombre
            for codigo, resp in op["responses"].items():
                assert resp["content"]["application/json"].get("example") is not None, f"{nombre} {codigo}"
            if op["x-estado"] == "implementado":
                assert any(c.startswith("2") for c in op["responses"]), nombre
            else:
                assert "501" in op["responses"], nombre
            if metodo in {"post", "patch"}:
                assert "example" in op["requestBody"]["content"]["application/json"], nombre
            protegida = not ruta.startswith(("/catalogo", "/health", "/openapi", "/auth/"))
            if protegida:
                assert "401" in op["responses"], nombre
            for nombre_param in [p[1:-1] for p in ruta.split("/") if p.startswith("{")]:
                assert any(p.get("name") == nombre_param for p in op.get("parameters", [])), nombre


def test_ejemplos_de_openapi_coinciden_con_la_api(client):
    """Los ejemplos públicos se generaron llamando a la API: siguen coincidiendo con la respuesta actual."""
    spec = yaml.safe_load((RAIZ / "openapi.yaml").read_text(encoding="utf-8"))
    ejemplo = spec["paths"]["/catalogo/fertilizantes/{fert_id}"]["get"]["responses"]["200"]["content"]["application/json"]["example"]
    actual = client.get("/api/v1/catalogo/fertilizantes/superfosfato-simple").get_json()
    assert ejemplo["composicion_referencial"] == actual["composicion_referencial"]
