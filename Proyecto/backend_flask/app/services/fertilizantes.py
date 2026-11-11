"""Catálogo de fertilizantes con composición de referencia y fuente citada.

Lee data/fertilizantes.yaml (sin ejecutar código), valida que cada dato tenga fuente y ofrece:
- consulta y filtro de fertilizantes por nutriente o grupo,
- cálculo de cuánto producto cubre un requerimiento de nutriente que entrega el usuario,
- conversión P2O5 <-> P y K2O <-> K con los factores de la guía FAO/IFA,
- revisión de una etiqueta contra los contenidos mínimos de la Resolución SAG 8.651/2024.

No recomienda dosis: el requerimiento lo ingresa el usuario (análisis de suelo o asesoría técnica).
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
import re
import unicodedata

import yaml

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "fertilizantes.yaml"
ESTADOS = {"cotejada_con_fuente", "citada_sin_cotejar"}
HOSTS_FUENTE = {
    "www.fertilizer.org",
    "agris.fao.org",
    "www.diariooficial.interior.gob.cl",
}
OXIDOS_SAG = ("N", "P2O5", "K2O", "MgO", "CaO", "SO3", "Na2O")


class FertilizanteError(ValueError):
    pass


def _norm(text):
    value = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in value if not unicodedata.combining(c)).casefold()


def _rango(valor):
    """Devuelve (mínimo, máximo) como Decimal a partir de un número o de [mín, máx]."""
    if isinstance(valor, list):
        if len(valor) != 2:
            raise RuntimeError("Un rango debe tener mínimo y máximo")
        bajo, alto = (Decimal(str(v)) for v in valor)
    else:
        bajo = alto = Decimal(str(valor))
    if not (Decimal(0) < bajo <= alto <= Decimal(100)):
        raise RuntimeError("Porcentaje fuera de 0-100")
    return bajo, alto


def _url_valida(url):
    u = urlparse(url or "")
    return u.scheme == "https" and u.hostname in HOSTS_FUENTE


@lru_cache(maxsize=1)
def cargar():
    """Lee y valida el archivo; un dato sin fuente o mal formado impide arrancar."""
    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for campo in ("fuentes", "nutrientes", "grupos", "fertilizantes", "conversiones", "normativa_contenidos_minimos"):
        if campo not in data:
            raise RuntimeError(f"Falta sección: {campo}")
    fuentes_ids = set()
    for fuente in data["fuentes"]:
        if not _url_valida(fuente.get("url")) or ("registro_fao" in fuente and not _url_valida(fuente["registro_fao"])):
            raise RuntimeError(f"URL de fuente no admitida: {fuente.get('id')}")
        fuentes_ids.add(fuente["id"])
    nutrientes = {n["id"] for n in data["nutrientes"]}
    grupos = {g["id"] for g in data["grupos"]}
    vistos = set()
    for fert in data["fertilizantes"]:
        if fert["id"] in vistos or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fert["id"]):
            raise RuntimeError(f"ID de fertilizante duplicado o inválido: {fert['id']}")
        vistos.add(fert["id"])
        if fert["grupo"] not in grupos or fert["fuente_id"] not in fuentes_ids:
            raise RuntimeError(f"Grupo o fuente inexistente: {fert['id']}")
        if not fert.get("ubicacion") or fert.get("estado_verificacion") not in ESTADOS:
            raise RuntimeError(f"Falta ubicación o estado de verificación: {fert['id']}")
        if not fert["nutrientes"] or set(fert["nutrientes"]) - nutrientes:
            raise RuntimeError(f"Nutriente desconocido: {fert['id']}")
        for valor in fert["nutrientes"].values():
            _rango(valor)
    if data["conversiones"]["fuente_id"] not in fuentes_ids:
        raise RuntimeError("Conversiones sin fuente")
    norma = data["normativa_contenidos_minimos"]
    if norma["fuente_id"] not in fuentes_ids:
        raise RuntimeError("Normativa sin fuente")
    for clave in ("un_macronutriente", "varios_macronutrientes"):
        if set(norma[clave]["minimos_pct"]) != set(OXIDOS_SAG):
            raise RuntimeError("Mínimos SAG incompletos")
    return data


def _fuentes_por_id():
    return {f["id"]: f for f in cargar()["fuentes"]}


def _num(valor):
    """Número JSON: entero si no tiene decimales."""
    valor = Decimal(str(valor))
    return int(valor) if valor == valor.to_integral_value() else float(valor)


def _composicion(fert):
    salida = {}
    for nutriente, valor in fert["nutrientes"].items():
        bajo, alto = _rango(valor)
        salida[nutriente] = {"min_pct": _num(bajo), "max_pct": _num(alto), "es_rango": bajo != alto}
    return salida


def _ficha(fert):
    grado = []
    for nutriente in ("N", "P2O5", "K2O"):
        valor = fert["nutrientes"].get(nutriente, 0)
        texto = "-".join(str(_num(v)) for v in valor) if isinstance(valor, list) else str(_num(valor))
        grado.append(texto.replace(".", ","))  # notación chilena: 34,5
    return {
        "id": fert["id"],
        "nombre": fert["nombre"],
        "formula": fert.get("formula"),
        "grupo": fert["grupo"],
        "grado_npk": " / ".join(grado),
        "composicion": _composicion(fert),
        "ubicacion_en_fuente": fert["ubicacion"],
        "estado_verificacion": fert["estado_verificacion"],
        "nota": fert.get("nota"),
        "fuente": _fuentes_por_id()[fert["fuente_id"]],
    }


def resumen():
    data = cargar()
    return {
        "version": data["version"],
        "fecha_consulta": data["fecha_consulta"],
        "aviso": data["aviso_general"],
        "nutrientes": data["nutrientes"],
        "grupos": data["grupos"],
        "fuentes": data["fuentes"],
        "total_fertilizantes": len(data["fertilizantes"]),
    }


def listar(q="", nutriente="", grupo=""):
    data = cargar()
    if nutriente and nutriente not in {n["id"] for n in data["nutrientes"]}:
        raise FertilizanteError("Nutriente desconocido. Usa N, P2O5, K2O, Mg o S")
    if grupo and grupo not in {g["id"] for g in data["grupos"]}:
        raise FertilizanteError("Grupo desconocido")
    if len(q) > 100:
        raise FertilizanteError("La búsqueda no puede superar 100 caracteres")
    encontrados = [
        _ficha(f)
        for f in data["fertilizantes"]
        if (not nutriente or nutriente in f["nutrientes"])
        and (not grupo or f["grupo"] == grupo)
        and (not q or _norm(q) in _norm(" ".join((f["id"], f["nombre"], f.get("formula") or ""))))
    ]
    return {"total": len(encontrados), "resultados": encontrados, "aviso": data["aviso_general"]}


def detalle(fert_id):
    for fert in cargar()["fertilizantes"]:
        if fert["id"] == fert_id:
            return _ficha(fert)
    return None


def _positivo(payload, campo, maximo, requerido=True):
    if campo not in payload:
        if requerido:
            raise FertilizanteError(f"Falta {campo}")
        return None
    valor = payload[campo]
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise FertilizanteError(f"{campo} debe ser un número")
    try:
        dec = Decimal(str(valor))
    except InvalidOperation:
        raise FertilizanteError(f"{campo} inválido")
    if not dec.is_finite() or not (Decimal(0) < dec <= Decimal(str(maximo))):
        raise FertilizanteError(f"{campo} debe ser mayor que cero y no superar {maximo}")
    return dec


def _r(valor, decimales="0.01"):
    return float(valor.quantize(Decimal(decimales), rounding=ROUND_HALF_UP))


def calcular(payload):
    """Kilos de producto para aportar el requerimiento indicado por el usuario."""
    if not isinstance(payload, dict):
        raise FertilizanteError("Enviar un objeto JSON")
    permitidos = {
        "fertilizante_id",
        "nutriente",
        "requerimiento_kg_ha",
        "superficie_ha",
        "superficie_m2",
        "ley_declarada_pct",
        "peso_saco_kg",
    }
    sobrantes = set(payload) - permitidos
    if sobrantes:
        raise FertilizanteError("Campos no admitidos: " + ", ".join(sorted(sobrantes)))
    fert = next((f for f in cargar()["fertilizantes"] if f["id"] == payload.get("fertilizante_id")), None)
    if fert is None:
        raise FertilizanteError("Fertilizante desconocido")
    nutriente = payload.get("nutriente")
    if nutriente not in fert["nutrientes"]:
        raise FertilizanteError(
            f"{fert['nombre']} no aporta {nutriente or 'ese nutriente'} según la fuente. "
            f"Aporta: {', '.join(fert['nutrientes'])}"
        )
    if ("superficie_ha" in payload) == ("superficie_m2" in payload):
        raise FertilizanteError("Indica superficie_ha O superficie_m2, no ambas")
    hectareas = (
        _positivo(payload, "superficie_ha", 100000)
        if "superficie_ha" in payload
        else _positivo(payload, "superficie_m2", 1000000000) / Decimal(10000)
    )
    requerimiento = _positivo(payload, "requerimiento_kg_ha", 2000)
    bajo, alto = _rango(fert["nutrientes"][nutriente])
    ley = _positivo(payload, "ley_declarada_pct", 100, requerido=False)
    if ley is None:
        if bajo != alto:
            raise FertilizanteError(
                f"La fuente da un rango de {_num(bajo)}-{_num(alto)} % de {nutriente}: "
                "indica en ley_declarada_pct el valor que declara la etiqueta de tu producto"
            )
        ley = bajo
        origen_ley = "referencia_fuente"
    else:
        origen_ley = "etiqueta_usuario"
    peso_saco = _positivo(payload, "peso_saco_kg", 1000, requerido=False)

    producto_ha = requerimiento * Decimal(100) / ley
    total = producto_ha * hectareas
    aportes = []
    for otro, valor in fert["nutrientes"].items():
        if otro == nutriente:
            continue
        o_bajo, o_alto = _rango(valor)
        aportes.append(
            {
                "nutriente": otro,
                "min_kg_ha": _r(producto_ha * o_bajo / 100),
                "max_kg_ha": _r(producto_ha * o_alto / 100),
            }
        )
    advertencias = [
        "El requerimiento lo ingresaste tú: este cálculo no recomienda dosis.",
        "Usa la ley que declara la etiqueta del producto que vas a comprar.",
    ]
    if origen_ley == "etiqueta_usuario" and not (bajo <= ley <= alto):
        advertencias.append(
            f"La ley indicada ({_num(ley)} %) está fuera del rango de referencia {_num(bajo)}-{_num(alto)} %: revisa la etiqueta."
        )
    if fert["estado_verificacion"] != "cotejada_con_fuente":
        advertencias.append("Composición de referencia sin cotejo completo: confirma con la etiqueta.")
    resultado = {
        "fertilizante": {"id": fert["id"], "nombre": fert["nombre"]},
        "nutriente": nutriente,
        "requerimiento_kg_ha": _r(requerimiento),
        "ley_usada_pct": _num(ley),
        "origen_ley": origen_ley,
        "superficie_ha": _r(hectareas, "0.0001"),
        "producto_kg_ha": _r(producto_ha),
        "producto_total_kg": _r(total),
        "aportes_adicionales_kg_ha": aportes,
        "fuente": _fuentes_por_id()[fert["fuente_id"]],
        "advertencias": advertencias,
    }
    if peso_saco is not None:
        sacos = int((total / peso_saco).to_integral_value(rounding=ROUND_CEILING))
        resultado["sacos"] = {
            "peso_saco_kg": _num(peso_saco),
            "cantidad": sacos,
            "sobrante_kg": _r(peso_saco * sacos - total),
        }
    return resultado


def conversiones():
    data = cargar()["conversiones"]
    return {**data, "fuente": _fuentes_por_id()[data["fuente_id"]]}


def convertir(de, a, valor_texto):
    factor = next((c["factor"] for c in cargar()["conversiones"]["factores"] if c["de"] == de and c["a"] == a), None)
    if factor is None:
        raise FertilizanteError("Conversión no disponible. Usa P2O5↔P o K2O↔K")
    try:
        valor = Decimal(str(valor_texto))
    except InvalidOperation:
        raise FertilizanteError("valor debe ser un número")
    if not valor.is_finite() or not (Decimal(0) <= valor <= Decimal(1000000)):
        raise FertilizanteError("valor debe estar entre 0 y 1.000.000")
    return {
        "de": de,
        "a": a,
        "valor": _num(valor),
        "factor": factor,
        "resultado": _r(valor * Decimal(str(factor)), "0.0001"),
        "fuente": _fuentes_por_id()[cargar()["conversiones"]["fuente_id"]],
    }


def normativa():
    data = cargar()["normativa_contenidos_minimos"]
    return {**data, "fuente": _fuentes_por_id()[data["fuente_id"]]}


def revisar_etiqueta(payload):
    """Compara los nutrientes declarados con los mínimos de la Res. SAG 8.651/2024 (grupo 2)."""
    if not isinstance(payload, dict) or not payload:
        raise FertilizanteError("Envía los nutrientes declarados, por ejemplo {\"N\": 46}")
    sobrantes = set(payload) - set(OXIDOS_SAG)
    if sobrantes:
        raise FertilizanteError(
            "Nutrientes no admitidos: " + ", ".join(sorted(sobrantes)) + ". Usa " + ", ".join(OXIDOS_SAG)
        )
    declarados = {}
    for clave in payload:
        declarados[clave] = _positivo(payload, clave, 100)
    norma = normativa()
    tipo = "un_macronutriente" if len(declarados) == 1 else "varios_macronutrientes"
    minimos = norma[tipo]["minimos_pct"]
    detalle_nutrientes = []
    for clave, valor in declarados.items():
        minimo = Decimal(str(minimos[clave]))
        detalle_nutrientes.append(
            {
                "nutriente": clave,
                "declarado_pct": _num(valor),
                "minimo_pct": _num(minimo),
                "cumple": valor >= minimo,
            }
        )
    return {
        "tipo": tipo,
        "descripcion": norma[tipo]["descripcion"],
        "cumple_todos": all(d["cumple"] for d in detalle_nutrientes),
        "nutrientes": detalle_nutrientes,
        "vigencia": norma["vigencia"],
        "fuente": norma["fuente"],
        "aviso": "Revisión orientativa de los contenidos mínimos; no reemplaza el análisis oficial ni el resto de exigencias de la norma.",
    }
