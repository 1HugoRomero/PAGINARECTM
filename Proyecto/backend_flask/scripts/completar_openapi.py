"""Completa openapi.yaml con descripciones, ejemplos REALES de solicitud y respuesta, códigos de error y fuente.

Los ejemplos no se escriben a mano: el script llama a cada endpoint de la propia API con una base de PRUEBA
(tests/helpers.py) y copia la respuesta obtenida. Así la documentación no puede inventar datos.

Uso (desde Proyecto/backend_flask):  python scripts/completar_openapi.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app import create_app  # noqa: E402
from tests.helpers import SECRETO, cabeceras, crear_bd  # noqa: E402

ESPEC = RAIZ / "openapi.yaml"
METODOS = ("get", "post", "patch", "delete", "put")
VALORES_RUTA = {
    "predio_id": "1",
    "potrero_id": "1",
    "cultivo_id": "1",
    "insumo_id": "1",
    "actividad_id": "1",
    "temporada_id": "1",
    "product_id": "fungisei",
    "fert_id": "superfosfato-simple",
}
CONSULTAS = {
    "/catalogo/convertir": "de=P2O5&a=P&valor=46",
    "/catalogo/fertilizantes": "nutriente=S",
    "/catalogo/productos": "categoria=fungicidas",
}
CUERPOS = {
    "/catalogo/calcular-fertilizante": {
        "fertilizante_id": "urea", "nutriente": "N", "requerimiento_kg_ha": 92, "superficie_ha": 2, "peso_saco_kg": 25,
    },
    "/catalogo/revisar-etiqueta": {
        "categoria": "inorganico", "nutrientes": {"N": 46}, "contiene_urea": True, "biuret_pct": 1,
    },
    "/catalogo/calcular-sacos": {
        "referencia_id": "trigo-invierno", "superficie_ha": 1.5, "peso_saco_kg": 25, "dosis_kg_ha": 180,
    },
}
CUERPOS_INVALIDOS = {
    "/catalogo/calcular-fertilizante": {"fertilizante_id": "superfosfato-simple", "nutriente": "K2O", "requerimiento_kg_ha": 40, "superficie_ha": 1},
    "/catalogo/revisar-etiqueta": {"categoria": "inorganico", "nutrientes": {"S": 10}},
    "/catalogo/calcular-sacos": {"referencia_id": "trigo-invierno", "superficie_ha": 1, "peso_saco_kg": 25, "dosis_kg_ha": 999},
}
CONSULTAS_INVALIDAS = {
    "/catalogo/convertir": "de=N&a=P&valor=1",
    "/catalogo/fertilizantes": "nutriente=Zn",
    "/catalogo/productos": "categoria=inventada",
}
FUENTE_CATALOGO = "data/catalogo_agricola.yaml: fichas SAG (etiquetas publicadas), INIA (publicaciones técnicas) y ODEPA."
FUENTE_FERTILIZANTES = (
    "data/fertilizantes.yaml: FAO/IFA, «Los fertilizantes y su uso», 4.ª ed., 2002 (Cuadros 2 y 3, pp. 38-39; "
    "Anexo p. 77) y Resolución SAG N° 8.651 exenta de 2024 (Diario Oficial, 18-12-2024)."
)
FUENTE_BD = "Base de datos oficial de AgroAsesor (Django), abierta en modo solo lectura y filtrada por el usuario firmado."


def _publica(ruta):
    return ruta.startswith(("/catalogo", "/health", "/openapi", "/auth/"))


def _admin(ruta):
    return ruta.startswith("/admin")


def _fuente(ruta):
    if ruta.startswith(("/catalogo/fertilizantes", "/catalogo/calcular-fertilizante", "/catalogo/conver",
                        "/catalogo/normativa", "/catalogo/revisar-etiqueta")):
        return FUENTE_FERTILIZANTES
    if ruta.startswith("/catalogo"):
        return FUENTE_CATALOGO
    if ruta in ("/health", "/openapi.json"):
        return "Estado del servicio y especificación (sin datos agrícolas)."
    return FUENTE_BD


def _recortar(dato, n=2):
    """Acorta listas largas para que el ejemplo sea legible (la estructura es la misma)."""
    if isinstance(dato, list):
        return [_recortar(x, n) for x in dato[:n]]
    if isinstance(dato, dict):
        return {k: _recortar(v, n) for k, v in dato.items()}
    return dato


def _llamar(cliente, metodo, ruta, consulta="", cuerpo=None, firmar=True, admin=False, crudo=None, usuario=None):
    destino = "/api/v1" + ruta + ("?" + consulta if consulta else "")
    datos = crudo if crudo is not None else (json.dumps(cuerpo).encode() if cuerpo is not None else b"")
    h = {}
    if firmar:
        h = cabeceras(usuario or (3 if admin else 1), admin, metodo.upper(), destino, datos)
    if cuerpo is not None and crudo is None:
        h["Content-Type"] = "application/json"
    elif crudo is not None:
        h["Content-Type"] = "text/plain"
    r = cliente.open(destino, method=metodo.upper(), data=datos or None, headers=h)
    try:
        return r.status_code, r.get_json()
    except Exception:  # noqa: BLE001
        return r.status_code, None


def _poner(op, status, ejemplo, descripcion=None):
    status = str(status)
    resp = op.setdefault("responses", {}).setdefault(status, {"description": descripcion or "Respuesta"})
    if descripcion and not resp.get("description"):
        resp["description"] = descripcion
    media = resp.setdefault("content", {}).setdefault("application/json", {})
    media.setdefault("schema", {"$ref": "#/components/schemas/Error"} if status[0] in "45" else {"type": "object"})
    if ejemplo is not None:
        media["example"] = _recortar(ejemplo)


def main():
    spec = yaml.safe_load(ESPEC.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        bd = crear_bd(Path(tmp) / "doc.sqlite3")
        cliente = create_app({"TESTING": True, "AGROASESOR_DB_PATH": bd, "AGROASESOR_INTERNAL_SECRET": SECRETO}).test_client()
        sin_bd = create_app({"TESTING": True, "AGROASESOR_DB_PATH": "", "AGROASESOR_INTERNAL_SECRET": ""}).test_client()
        for plantilla, operaciones in spec["paths"].items():
            ruta = plantilla
            for nombre, valor in VALORES_RUTA.items():
                ruta = ruta.replace("{" + nombre + "}", valor)
            for metodo, op in operaciones.items():
                if metodo not in METODOS:
                    continue
                publica, admin = _publica(plantilla), _admin(plantilla)
                cuerpo = CUERPOS.get(plantilla, {} if metodo in ("post", "patch") else None)
                status, j = _llamar(cliente, metodo, ruta, CONSULTAS.get(plantilla, ""), cuerpo, firmar=not publica, admin=admin)
                if plantilla == "/openapi.json":  # la especificación completa no se copia dentro de sí misma
                    j = {"openapi": "3.0.3", "info": {"title": spec["info"]["title"]}, "paths": {"...": "..."}}
                _poner(op, status, j, "Respuesta de ejemplo")
                if plantilla == "/usuarios/me" and metodo == "get":
                    s404, j404 = _llamar(cliente, metodo, ruta, usuario=4)  # cuenta inactiva de la base de prueba
                    _poner(op, s404, j404, "La cuenta no existe o está inactiva")
                if plantilla == "/health":
                    s503, j503 = _llamar(sin_bd, metodo, ruta, "", None, firmar=False)
                    _poner(op, s503, j503, "La base de datos no está configurada o no responde")

                # Solicitud de ejemplo
                if metodo in ("post", "patch"):
                    rb = op.setdefault("requestBody", {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}})
                    rb.setdefault("content", {}).setdefault("application/json", {}).setdefault("schema", {"type": "object"})
                    rb["content"]["application/json"]["example"] = cuerpo
                # Errores
                if not publica:
                    s401, j401 = _llamar(cliente, metodo, ruta, "", cuerpo, firmar=False)
                    _poner(op, s401, j401, "Sin autenticación de Django válida o firma vencida")
                    s503, j503 = _llamar(sin_bd, metodo, ruta, "", cuerpo, firmar=False)
                    _poner(op, s503, j503, "API sin clave interna o sin base de datos configurada")
                if admin:
                    s403, j403 = _llamar(cliente, metodo, ruta, "", cuerpo, firmar=True, admin=False)
                    _poner(op, s403, j403, "El usuario no es administrador")
                if "{" in plantilla and status == 200:
                    otra = ruta.replace("/1", "/99999").replace("superfosfato-simple", "no-existe").replace("fungisei", "no-existe")
                    s404, j404 = _llamar(cliente, metodo, otra, "", cuerpo, firmar=not publica)
                    if s404 == 404:
                        _poner(op, 404, j404, "No existe o pertenece a otro agricultor")
                if plantilla in CUERPOS_INVALIDOS:
                    s400, j400 = _llamar(cliente, metodo, ruta, "", CUERPOS_INVALIDOS[plantilla], firmar=False)
                    _poner(op, s400, j400, "Datos inválidos")
                    s415, j415 = _llamar(cliente, metodo, ruta, "", None, firmar=False, crudo=b"texto")
                    _poner(op, s415, j415, "Se requiere application/json")
                if plantilla in CONSULTAS_INVALIDAS:
                    s400, j400 = _llamar(cliente, metodo, ruta, CONSULTAS_INVALIDAS[plantilla], None, firmar=not publica)
                    _poner(op, s400, j400, "Parámetros inválidos")

                op["x-fuente-datos"] = _fuente(plantilla)
                if not op.get("description"):
                    acceso = "Pública (sin sesión)." if publica else (
                        "Requiere sesión de Django (administrador)." if admin else "Requiere sesión de Django; solo datos del propio agricultor."
                    )
                    op["description"] = f"{op.get('summary', '')}. {acceso}"
                if status == 501:
                    op["x-estado"] = "pendiente"
                    op["description"] = op["description"].rstrip() + " PENDIENTE: responde 501 hasta que se implemente."
                else:
                    op["x-estado"] = "implementado"
    ESPEC.write_text(
        "# AgroAsesor API · ejemplos generados por scripts/completar_openapi.py (no editar los ejemplos a mano)\n"
        + yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=110),
        encoding="utf-8",
    )
    print("openapi.yaml actualizado")


if __name__ == "__main__":
    main()
