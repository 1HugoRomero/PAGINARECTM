"""Consulta local y segura de catálogo con procedencia institucional.

Este módulo no conecta la base de datos oficial ni descarga datos en vivo.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
import re
import unicodedata

import yaml

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "catalogo_agricola.yaml"
# citada_sin_cotejar: el valor viene de una publicación institucional citada, pero aún no se cotejó con el documento.
ESTADOS_REFERENCIA = {"cotejada_con_fuente", "citada_sin_cotejar"}
OFFICIAL_HOSTS = {
    "www.sag.gob.cl",
    "sag.gob.cl",
    "www.sag.cl",
    "sag.cl",
    "www.inia.cl",
    "inia.cl",
    "biblioteca.inia.cl",
    "planpredial.inia.cl",
    "www.odepa.gob.cl",
    "odepa.gob.cl",
}


class CatalogoError(ValueError):
    pass


def _norm(text):
    value = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in value if not unicodedata.combining(c)).casefold()


@lru_cache(maxsize=1)
def cargar_catalogo():
    """Lee YAML confiable, sin ejecutar código, y verifica referencias cruzadas."""
    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise RuntimeError("Catálogo YAML inválido")
    for field in ("fuentes", "categorias", "productos", "referencias_siembra"):
        if not isinstance(data.get(field), list):
            raise RuntimeError(f"Falta sección: {field}")
    ids_fuente = set()
    for source in data["fuentes"]:
        if source.get("id") in ids_fuente:
            raise RuntimeError("ID de fuente duplicado")
        ids_fuente.add(source["id"])
        u = urlparse(source.get("url", ""))
        if u.scheme != "https" or u.hostname not in OFFICIAL_HOSTS:
            raise RuntimeError(f"URL no institucional: {source.get('id')}")
    ids_categorias = {c["id"] for c in data["categorias"]}
    if len(ids_categorias) != len(data["categorias"]):
        raise RuntimeError("Categoría duplicada")
    ids_productos = set()
    for product in data["productos"]:
        if product["id"] in ids_productos or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", product["id"]):
            raise RuntimeError("ID de producto duplicado o inválido")
        ids_productos.add(product["id"])
        if product["categoria"] not in ids_categorias or not product.get("fuente_ids"):
            raise RuntimeError(f"Producto sin categoría o fuentes: {product['id']}")
        if any(fid not in ids_fuente for fid in product["fuente_ids"]):
            raise RuntimeError(f"Fuente inexistente para producto {product['id']}")
        if product.get("precio_clp") is not None or product.get("presentaciones_comerciales_verificadas"):
            raise RuntimeError("Este borrador no admite precios ni envases comerciales no cotejados")
        if (
            product["clase"] == "producto_con_etiqueta_sag"
            and product.get("estado_autorizacion") != "requiere_cotejo_vigente"
        ):
            raise RuntimeError("No afirmar registro vigente sin cotejo del SAG")
    for ref in data["referencias_siembra"]:
        if ref["fuente_id"] not in ids_fuente:
            raise RuntimeError("Referencia sin fuente")
        if not (0 < ref["dosis_min_kg_ha"] <= ref["dosis_max_kg_ha"]):
            raise RuntimeError("Rango de dosis inválido")
        if ref.get("estado_verificacion") not in ESTADOS_REFERENCIA:
            raise RuntimeError(f"Referencia sin estado de verificación válido: {ref.get('id')}")
        if ref["estado_verificacion"] == "cotejada_con_fuente" and not ref.get("fecha_consulta"):
            raise RuntimeError(f"Referencia cotejada sin fecha de consulta: {ref.get('id')}")
    return data


def fuentes():
    return cargar_catalogo()["fuentes"]


def categorias():
    return cargar_catalogo()["categorias"]


def _enriquecer(producto):
    fuentes_por_id = {f["id"]: f for f in fuentes()}
    return {**producto, "fuentes": [fuentes_por_id[i] for i in producto["fuente_ids"]]}


def productos(q="", categoria="", pagina=1, limite=20):
    data = cargar_catalogo()
    if categoria and categoria not in {c["id"] for c in data["categorias"]}:
        raise CatalogoError("Categoría desconocida")
    if len(q) > 100:
        raise CatalogoError("La búsqueda no puede superar 100 caracteres")
    if not 1 <= pagina <= 100000 or not 1 <= limite <= 100:
        raise CatalogoError("Paginación fuera de rango")
    found = [
        p
        for p in data["productos"]
        if (not categoria or p["categoria"] == categoria)
        and (not q or _norm(q) in _norm(" ".join((p["nombre"], p["descripcion"], p["categoria"]))))
    ]
    total = len(found)
    start = (pagina - 1) * limite
    return {
        "total": total,
        "pagina": pagina,
        "limite": limite,
        "resultados": [_enriquecer(p) for p in found[start : start + limite]],
        "aviso": data["aviso_general"],
    }


def producto_por_id(product_id):
    for p in cargar_catalogo()["productos"]:
        if p["id"] == product_id:
            return _enriquecer(p)
    return None


def referencias_siembra():
    src = {s["id"]: s for s in fuentes()}
    return [{**ref, "fuente": src[ref["fuente_id"]]} for ref in cargar_catalogo()["referencias_siembra"]]


def _decimal_positivo(value, field, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise CatalogoError(f"{field} debe ser un número positivo, no texto ni booleano")
    try:
        val = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise CatalogoError(f"{field} inválido")
    if not val.is_finite() or not (Decimal('0') < val <= Decimal(str(maximum))):
        raise CatalogoError(f"{field} debe ser mayor que cero y no superar {maximum}")
    return val


def calcular_sacos(payload):
    """Cálculo de logística para semillas. NO aplica a plaguicidas/fertilizantes."""
    if not isinstance(payload, dict):
        raise CatalogoError("Enviar objeto JSON")
    allowed = {"referencia_id", "superficie_ha", "superficie_m2", "peso_saco_kg", "dosis_kg_ha", "precio_saco_clp"}
    if set(payload) - allowed:
        raise CatalogoError("Campos no admitidos: " + ", ".join(sorted(set(payload) - allowed)))
    has_ha = "superficie_ha" in payload
    has_m2 = "superficie_m2" in payload
    if has_ha == has_m2:
        raise CatalogoError("Indicar superficie_ha O superficie_m2, no ambas")
    ref = next((r for r in referencias_siembra() if r["id"] == payload.get("referencia_id")), None)
    if ref is None:
        raise CatalogoError("Referencia de siembra desconocida")
    ha = (
        _decimal_positivo(payload["superficie_ha"], "superficie_ha", 100000)
        if has_ha
        else _decimal_positivo(payload["superficie_m2"], "superficie_m2", 1000000000) / Decimal(10000)
    )
    peso = _decimal_positivo(payload.get("peso_saco_kg"), "peso_saco_kg", 1000)
    dosis = _decimal_positivo(payload.get("dosis_kg_ha"), "dosis_kg_ha", 100000)
    if not Decimal(str(ref["dosis_min_kg_ha"])) <= dosis <= Decimal(str(ref["dosis_max_kg_ha"])):
        raise CatalogoError("Dosis fuera del rango de referencia INIA; revisar sistema, variedad y condiciones")
    precio = (
        _decimal_positivo(payload["precio_saco_clp"], "precio_saco_clp", 1000000000)
        if "precio_saco_clp" in payload
        else None
    )
    if precio is not None and precio != precio.to_integral_value():
        raise CatalogoError("precio_saco_clp debe expresarse en pesos enteros")
    total = ha * dosis
    sacos = int((total / peso).to_integral_value(rounding=ROUND_CEILING))
    redondear = lambda x: float(x.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    return {
        "referencia_id": ref["id"],
        "cultivo": ref["cultivo"],
        "sistema": ref["sistema"],
        "superficie_ha": redondear(ha),
        "dosis_elegida_kg_ha": redondear(dosis),
        "peso_saco_simulado_kg": redondear(peso),
        "semilla_requerida_kg": redondear(total),
        "sacos_necesarios": sacos,
        "capacidad_total_comprada_kg": redondear(peso * sacos),
        "sobrante_teorico_kg": redondear(peso * sacos - total),
        "costo_estimado_clp": int(precio * sacos) if precio is not None else None,
        "fuente": ref["fuente"],
        "advertencia": "Cálculo orientativo para compra. El tamaño de saco lo ingresa el usuario; no representa un producto comercial verificado. Confirmar dosis con asesoría técnica y datos del lote.",
    }
